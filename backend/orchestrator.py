"""
OSOCC Orchestrator.

Runs the full UNDAC operating cycle over an incident, chaining the agentic cells
in the order an On-Site Operations Coordination Centre would:

    Ingestion → Assessment (MIRA) → Coordination (3W/OSOCC)
              → Logistics → Information Management (SitRep) → Alerts

It streams per-step events through an async callback so the UI can render the
agents "thinking" live, and pauses before resource commitment for Human-In-The-
Loop (HITL) approval when required.
"""
from __future__ import annotations
import asyncio
from typing import Callable, Optional, Awaitable

from .models import Incident, DisasterIncident, GeoPoint
from .agents.ingestion import run_ingestion_agent
from .agents.assessment import run_assessment_agent
from .agents.coordination import run_coordination_agent
from .agents.logistics import run_logistics_agent
from .agents.infomanagement import run_im_agent
from .agents.alerts import run_alert_agent

EmitFn = Callable[[str, str, dict], Awaitable[None]]


async def run_osocc_pipeline(
    raw_report: str,
    sitrep_number: int = 1,
    commit_inventory: bool = True,
    auto_approve: bool = True,
    emit: Optional[EmitFn] = None,
    existing_incident: Optional[DisasterIncident] = None,
    override_lat: Optional[float] = None,
    override_lon: Optional[float] = None,
    override_location: Optional[str] = None,
    exposure_ref: Optional[dict] = None,
) -> Incident:
    """Execute the full pipeline. `emit(agent, message, payload)` is awaited for
    every step so callers (WebSocket handlers) can stream progress."""

    async def _emit(agent: str, message: str, payload: dict | None = None):
        if emit:
            await emit(agent, message, payload or {})

    # Sync emit shim for the (synchronous) agents — schedules onto the loop
    loop = asyncio.get_event_loop()

    def make_sync_emit(record: Incident):
        def sync_emit(agent: str, message: str):
            record.log(agent, message)
            if emit:
                asyncio.run_coroutine_threadsafe(
                    _emit(agent, message, {"step": agent}), loop
                )
        return sync_emit

    import time as _time
    _t0 = _time.time()

    # 1. Ingestion -----------------------------------------------------------
    await _emit("Orchestrator", "Starting OSOCC pipeline.", {"status": "New"})
    # temporary record to capture logs during ingestion
    if existing_incident is not None:
        di = existing_incident
    else:
        tmp = Incident(incident=DisasterIncident(raw_report=raw_report))
        di = await asyncio.to_thread(run_ingestion_agent, raw_report, make_sync_emit(tmp))

    # Pin to the EXACT crisis coordinates when the caller supplies them (e.g. a
    # live USGS/GDACS event) rather than relying on geocoding a place name,
    # which can drift to a country centroid.
    if override_lat is not None and override_lon is not None:
        di.coordinates = GeoPoint(lat=override_lat, lon=override_lon)
        if override_location:
            di.location = override_location

    record = Incident(incident=di, status="Assessing")
    record.log("Ingestion", f"Structured {di.disaster_type} @ {di.location}.")
    await _emit("Ingestion", f"Structured incident: {di.disaster_type} @ {di.location}.",
                {"incident": di.model_dump(), "status": "Assessing"})
    sync_emit = make_sync_emit(record)

    # 2. Assessment (MIRA) — grounded in real exposure when we have an event ref
    exposure = None
    if exposure_ref:
        from .data.exposure import resolve_exposure
        await _emit("Assessment", "Fetching real exposure data (USGS PAGER / GDACS)…", {})
        exposure = await asyncio.to_thread(resolve_exposure, exposure_ref)
        if exposure and exposure.get("available"):
            record.log("Assessment", f"Real exposure retrieved (alert={exposure.get('alert_level')}).")
    assessment = await asyncio.to_thread(run_assessment_agent, di, exposure, sync_emit)
    record.assessment = assessment
    await _emit("Assessment", f"Severity {assessment.severity_score} "
                f"({assessment.severity_index}/100).",
                {"assessment": assessment.model_dump()})

    # 2b. Analysis — context, corroboration, confidence, evidence, questions
    await _emit("Analysis", "Gathering on-the-ground context and corroborating sources…", {})
    from .data import context as ctx_mod, live_feeds
    from . import news as news_mod, analysis
    lat = di.coordinates.lat if di.coordinates else None
    lon = di.coordinates.lon if di.coordinates else None
    # context, media and the corroboration feed are independent → run concurrently
    context, media, all_events = await asyncio.gather(
        asyncio.to_thread(ctx_mod.get_context, lat, lon, di.disaster_type),
        asyncio.to_thread(news_mod.get_media, di.location, di.disaster_type),
        asyncio.to_thread(live_feeds.get_all_events, 2.5),
    )
    # earthquake ShakeMap (real shaking-intensity map) comes from the USGS detail
    if exposure and exposure.get("shakemap_url"):
        context["shakemap"] = {"url": exposure["shakemap_url"], "source": "USGS ShakeMap"}
    evidence, corroborating = analysis.build_evidence(di, assessment, exposure, all_events, media, context)
    confidence = analysis.build_confidence(exposure, corroborating, media,
                                           has_explicit_report=bool(di.estimated_affected or di.estimated_casualties))
    open_questions = analysis.build_open_questions(di, assessment, context)
    record.context = context
    record.evidence = evidence
    record.confidence = confidence
    record.open_questions = open_questions
    record.log("Analysis", f"Confidence {confidence.level} ({confidence.score}/100); "
               f"{len(evidence)} evidence items; {len(open_questions)} open questions.")
    await _emit("Analysis", f"Confidence: {confidence.level} ({confidence.score}/100) · "
                f"{len(open_questions)} open questions.",
                {"confidence": confidence.model_dump(),
                 "evidence": [e.model_dump() for e in evidence],
                 "open_questions": [q.model_dump() for q in open_questions],
                 "context": context})

    # 3. Coordination (OSOCC / 3W) ------------------------------------------
    record.status = "Coordinating"
    coordination = await asyncio.to_thread(run_coordination_agent, di, assessment, sync_emit)
    record.coordination = coordination
    await _emit("Coordination", f"3W matrix with {len(coordination.three_w)} entries.",
                {"coordination": coordination.model_dump(), "status": "Coordinating"})

    # 4. Logistics — HITL gate before committing inventory -------------------
    logistics = await asyncio.to_thread(
        run_logistics_agent, di, assessment, False, sync_emit  # dry-run first
    )
    record.logistics = logistics
    await _emit("Logistics", logistics.summary,
                {"logistics": logistics.model_dump(), "awaiting_approval": not auto_approve})

    if auto_approve:
        record.approved = True
        if commit_inventory:
            logistics = await asyncio.to_thread(
                run_logistics_agent, di, assessment, True, sync_emit
            )
            record.logistics = logistics
        await _emit("HITL", "Dispatch auto-approved; inventory committed.",
                    {"approved": True})
    else:
        record.approved = None  # caller will approve via API
        await _emit("HITL", "Awaiting human approval before committing resources.",
                    {"approved": None})

    # 5. Information Management (SitRep) -------------------------------------
    sitrep = await asyncio.to_thread(
        run_im_agent, sitrep_number, di, assessment, coordination, logistics, sync_emit
    )
    record.sitrep = sitrep
    await _emit("InfoManagement", "SitRep generated.",
                {"sitrep": sitrep.model_dump()})

    # 6. Alerts (Everbridge-style) ------------------------------------------
    notifications = await asyncio.to_thread(run_alert_agent, di, assessment, sync_emit)
    record.notifications = notifications
    await _emit("Alerts", f"{len(notifications)} notification(s) issued.",
                {"notifications": [n.model_dump() for n in notifications]})

    record.status = "Dispatched" if record.approved else "Coordinating"

    # metrics — value is measured in time-to-briefing and uncertainty
    elapsed = round(_time.time() - _t0, 1)
    open_q = len([q for q in record.open_questions if q.status == "Open"])
    record.metrics = {
        "time_to_brief_seconds": elapsed,
        "severity": assessment.severity_score,
        "confidence_level": confidence.level,
        "confidence_score": confidence.score,
        "open_questions": open_q,
        "evidence_count": len(record.evidence),
        "sources": confidence.corroborating_sources,
    }
    record.log("Orchestrator", f"Briefing package ready in {elapsed}s · "
               f"{assessment.severity_score}/{confidence.level} · {open_q} open questions.")
    await _emit("Orchestrator", f"Briefing package ready in {elapsed}s.",
                {"status": record.status, "incident_id": record.id, "metrics": record.metrics})
    return record
