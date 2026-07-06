"""
UNDAC Crisis Coordinator — FastAPI application.

Serves:
  * the EarthExplorer-style 3D-globe single-page frontend (static)
  * a REST API for live disaster feeds, the agent pipeline, incidents & inventory
  * a WebSocket that streams the agents' reasoning live as a pipeline runs

Run:  python -m uvicorn backend.app:app --reload  (from crisis_coordinator/)
or:   python run.py
"""
from __future__ import annotations
import os
import json
import asyncio
from typing import Optional

# load API keys from .env (gitignored) before anything reads os.environ
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm
from .store import STORE
from .orchestrator import run_osocc_pipeline
from .agents.logistics import run_logistics_agent
from .resources import STORE as RESOURCES, Resource
from .data import live_feeds
from .data.hazard_kb import HAZARD_PROFILES, list_hazards
from .monitor import ENGINE, WatchRule, Channels
from .models import Comment, Decision, Incident
from .briefing import render_briefing
from .agents.ingestion import run_ingestion_agent
from .skills.local_poi import fetch_local_pois

_HERE = os.path.dirname(__file__)
_FRONTEND = os.path.normpath(os.path.join(_HERE, "..", "frontend"))

app = FastAPI(title="UNDAC Crisis Coordinator", version="2.0")

# Poll interval for the background monitor (seconds)
_MONITOR_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "120"))


@app.on_event("startup")
async def _start_monitor():
    async def loop():
        # seed the backlog immediately so we only alert on new events
        try:
            await asyncio.to_thread(ENGINE.poll)
        except Exception:
            pass
        while True:
            await asyncio.sleep(_MONITOR_INTERVAL)
            try:
                await asyncio.to_thread(ENGINE.poll)
            except Exception:
                pass
    asyncio.create_task(loop())


# ---------------------------------------------------------------- API models
class RunRequest(BaseModel):
    report: str
    auto_approve: bool = True
    commit_inventory: bool = True
    lat: Optional[float] = None
    lon: Optional[float] = None
    location: Optional[str] = None
    exposure_ref: Optional[dict] = None


class PublicReportRequest(BaseModel):
    sender_phone: str
    message: str


# ---------------------------------------------------------------- meta / health
@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm.status(), "incidents": len(STORE.all())}


@app.get("/api/hazards")
def hazards():
    return {"hazards": list_hazards(), "profiles": HAZARD_PROFILES}


# ---------------------------------------------------------------- live feeds
@app.get("/api/events")
def events(min_magnitude: float = 4.5):
    """Aggregated live disaster events for the globe."""
    return {"events": live_feeds.get_all_events(min_magnitude)}


@app.get("/api/events/earthquakes")
def earthquakes(min_magnitude: float = 4.0, window: str = "all_day"):
    return {"events": live_feeds.get_usgs_earthquakes(min_magnitude, window)}


@app.get("/api/events/gdacs")
def gdacs():
    return {"events": live_feeds.get_gdacs_alerts()}


@app.get("/api/events/reliefweb")
def reliefweb(limit: int = 15):
    return {"events": live_feeds.get_reliefweb_disasters(limit)}


@app.get("/api/events/eonet")
def eonet(limit: int = 50):
    return {"events": live_feeds.get_eonet_events(limit)}


# ---------------------------------------------------------------- news & social
@app.get("/api/media")
def media(location: str = "", type: str = ""):
    from . import news
    return news.get_media(location, type)


@app.get("/api/news")
def news_endpoint(q: str, limit: int = 12):
    from . import news
    return {"news": news.get_news(q, limit)}


# ---------------------------------------------------------------- monitoring & alerts
@app.get("/api/monitor/status")
def monitor_status():
    return ENGINE.status()


@app.get("/api/monitor/rules")
def monitor_rules():
    return {"rules": [r.model_dump() for r in ENGINE.list_rules()]}


@app.post("/api/monitor/rules")
def monitor_add_rule(rule: WatchRule):
    return ENGINE.add_rule(rule).model_dump()


@app.delete("/api/monitor/rules/{rule_id}")
def monitor_delete_rule(rule_id: str):
    return {"deleted": ENGINE.delete_rule(rule_id)}


@app.get("/api/monitor/channels")
def monitor_get_channels():
    ch = ENGINE.channels
    return {"webhook_url": ch.webhook_url, "email_to": ch.email_to}


@app.post("/api/monitor/channels")
def monitor_set_channels(ch: Channels):
    ENGINE.set_channels(ch)
    return ENGINE.status()


@app.get("/api/monitor/alerts")
def monitor_alerts():
    return {"alerts": [a.model_dump() for a in ENGINE.alerts]}


@app.post("/api/monitor/poll")
def monitor_poll_now():
    fired = ENGINE.poll()
    return {"fired": fired, "status": ENGINE.status()}


@app.post("/api/monitor/test")
def monitor_test():
    """Send a sample alert through the configured channels so the user can
    verify delivery end-to-end."""
    sample = {
        "id": "test-" + os.urandom(3).hex(), "title": "TEST: simulated Red alert (no real event)",
        "type": "Earthquake", "severity": "Critical", "magnitude": 7.4,
        "country": "Test Region", "source": "SELF-TEST", "lat": 0, "lon": 0,
        "url": "https://earthquake.usgs.gov",
    }
    rule = WatchRule(name="Manual test")
    alert = ENGINE.dispatch(sample, rule)
    return alert.model_dump()


# ---------------------------------------------------------------- resource registry
@app.get("/api/resources")
def list_resources():
    return {"resources": [r.model_dump() for r in RESOURCES.all()],
            "totals": RESOURCES.totals_by_type()}


@app.post("/api/resources")
def create_resource(resource: Resource):
    return RESOURCES.create(resource.model_dump(exclude={"id", "updated_at"})).model_dump()


@app.put("/api/resources/{rid}")
def update_resource(rid: str, patch: dict):
    r = RESOURCES.update(rid, patch)
    if not r:
        raise HTTPException(404, "Resource not found")
    return r.model_dump()


@app.delete("/api/resources/{rid}")
def delete_resource(rid: str):
    return {"deleted": RESOURCES.delete(rid)}


# ---------------------------------------------------------------- incidents
@app.get("/api/incidents")
def incidents():
    return {"incidents": [i.model_dump() for i in STORE.all()]}


@app.get("/api/incidents/{incident_id}")
def incident(incident_id: str):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc.model_dump()


@app.post("/api/incidents/{incident_id}/approve")
async def approve(incident_id: str):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    if inc.approved:
        return {"status": "already approved"}
    # commit inventory now
    if inc.assessment:
        inc.logistics = await asyncio.to_thread(
            run_logistics_agent, inc.incident, inc.assessment, True
        )
    inc.approved = True
    inc.status = "Dispatched"
    inc.log("HITL", "Human approved dispatch; inventory committed.")
    STORE.update(inc)
    return {"status": "approved", "incident": inc.model_dump()}


@app.post("/api/public/report")
async def public_report(req: PublicReportRequest):
    import uuid
    # 1. AI Text Ingestion via run_ingestion_agent
    di = await asyncio.to_thread(run_ingestion_agent, req.message)
    
    # 2. Local POI Enrichment
    local_pois = []
    lat = di.coordinates.lat
    lon = di.coordinates.lon
    if lat is not None and lon is not None:
        local_pois = await asyncio.to_thread(fetch_local_pois, lat, lon, 1500)
        
    victim_id = f"vic-{uuid.uuid4().hex[:4]}"
    
    # Create the incident record
    record = Incident(
        id=victim_id,
        status="New",
        incident=di,
        local_pois=local_pois
    )
    record.log("Webhook", f"Received public distress report from {req.sender_phone}.")
    if local_pois:
        record.log("POI Enrichment", f"Enriched with {len(local_pois)} local POIs.")
        
    STORE.add(record)
    
    # WebSocket Broadcast
    event_data = {
        "event": "new_victim_report",
        "id": victim_id,
        "lat": lat,
        "lon": lon
    }
    await broadcast_live_event(event_data)
    
    return {"status": "success", "incident": record.model_dump()}


@app.post("/api/incidents/{incident_id}/dispatch")
async def dispatch_incident(incident_id: str):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
        
    # Deduct 1 rescue boat and 1 medic team
    allocated_boats = RESOURCES.consume("rescue_boats", 1)
    allocated_medics = RESOURCES.consume("medics", 1)
    
    inc.status = "Dispatched"
    inc.approved = True
    inc.log("HITL", f"Dispatched rescue resources. Allocated: {allocated_boats} rescue boats, {allocated_medics} medics.")
    STORE.update(inc)
    
    # WebSocket Broadcast update
    await broadcast_live_event({
        "event": "incident_updated",
        "id": incident_id,
        "status": "Dispatched"
    })
    
    return {"status": "success", "incident": inc.model_dump()}


class AckRequest(BaseModel):
    target: str            # "cluster:<id>" | "notification:<id>" | "question:<id>"
    status: str = "Accepted"   # Accepted | Rejected | Amended | Answered
    by: str = "operator"
    note: str = ""
    answer: str = ""


def _now_iso():
    import datetime
    return datetime.datetime.utcnow().isoformat() + "Z"


@app.post("/api/incidents/{incident_id}/ack")
def acknowledge(incident_id: str, req: AckRequest):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    kind, _, tid = req.target.partition(":")
    found = False
    if kind == "cluster" and inc.coordination:
        for e in inc.coordination.three_w:
            if e.id == tid:
                e.ack.status = req.status; e.ack.by = req.by
                e.ack.note = req.note or req.answer; e.ack.at = _now_iso()
                if req.status == "Amended" and req.answer:
                    e.what = req.answer
                found = True
    elif kind == "notification":
        for n in inc.notifications:
            if n.id == tid:
                n.ack.status = req.status; n.ack.by = req.by
                n.ack.note = req.note; n.ack.at = _now_iso(); found = True
    elif kind == "question":
        for q in inc.open_questions:
            if q.id == tid:
                q.status = "Answered" if req.status in ("Answered", "Accepted") else "Open"
                q.answer = req.answer or req.note; found = True
    if not found:
        raise HTTPException(404, "Ack target not found")
    inc.log("HITL", f"{req.by} {req.status.lower()} {req.target}"
            + (f": {req.note or req.answer}" if (req.note or req.answer) else ""))
    # keep open-question metric live
    if inc.metrics:
        inc.metrics["open_questions"] = len([q for q in inc.open_questions if q.status == "Open"])
    STORE.update(inc)
    return inc.model_dump()


@app.post("/api/incidents/{incident_id}/comments")
def add_comment(incident_id: str, comment: Comment):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    inc.comments.append(comment)
    inc.log(comment.author, f"comment: {comment.text}")
    STORE.update(inc)
    return inc.model_dump()


@app.post("/api/incidents/{incident_id}/decisions")
def add_decision(incident_id: str, decision: Decision):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    inc.decisions.append(decision)
    inc.log(decision.author, f"decision: {decision.decision}")
    STORE.update(inc)
    return inc.model_dump()


@app.get("/api/incidents/{incident_id}/briefing", response_class=HTMLResponse)
def briefing(incident_id: str):
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return HTMLResponse(render_briefing(inc))


@app.get("/api/incidents/{incident_id}/briefing/pdf")
def briefing_pdf(incident_id: str):
    from fastapi import Response
    from .briefing import render_briefing_pdf
    
    inc = STORE.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    try:
        pdf_data = render_briefing_pdf(inc)
    except Exception as e:
        raise HTTPException(500, f"Failed to generate PDF: {str(e)}")
    
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=orbit_briefing_{incident_id}.pdf"}
    )


@app.get("/api/context")
def context(lat: float, lon: float):
    from .data import context as ctx
    return ctx.get_context(lat, lon)


@app.get("/api/vessels")
def vessels(lat: float, lon: float):
    """Live vessel tracks near a point for the 3D globe."""
    from .data import context as ctx
    return ctx.get_vessel_tracks(lat, lon)


@app.post("/api/run")
async def run(req: RunRequest):
    """Run the full pipeline synchronously (non-streaming) and store the result."""
    n = STORE.next_sitrep_number()
    record = await run_osocc_pipeline(
        req.report, sitrep_number=n,
        commit_inventory=req.commit_inventory, auto_approve=req.auto_approve,
        override_lat=req.lat, override_lon=req.lon, override_location=req.location,
        exposure_ref=req.exposure_ref,
    )
    STORE.add(record)
    return record.model_dump()


_LIVE_SOCKETS: set[WebSocket] = set()


async def broadcast_live_event(data: dict):
    for ws in list(_LIVE_SOCKETS):
        try:
            await ws.send_json(data)
        except Exception:
            pass


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    _LIVE_SOCKETS.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        try:
            _LIVE_SOCKETS.remove(ws)
        except KeyError:
            pass


# ---------------------------------------------------------------- WebSocket (live agents)
@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()
    try:
        msg = await ws.receive_text()
        payload = json.loads(msg)
        report = payload.get("report", "")
        auto_approve = payload.get("auto_approve", True)
        commit = payload.get("commit_inventory", True)

        async def emit(agent: str, message: str, data: dict):
            await ws.send_json({"agent": agent, "message": message, "data": data})

        n = STORE.next_sitrep_number()
        record = await run_osocc_pipeline(
            report, sitrep_number=n, commit_inventory=commit,
            auto_approve=auto_approve, emit=emit,
            override_lat=payload.get("lat"), override_lon=payload.get("lon"),
            override_location=payload.get("location"),
            exposure_ref=payload.get("exposure_ref"),
        )
        STORE.add(record)
        await ws.send_json({"agent": "Done", "message": "complete",
                            "data": {"incident": record.model_dump()}})
    except WebSocketDisconnect:
        return
    except Exception as e:  # surface errors to the UI rather than dropping the socket
        try:
            await ws.send_json({"agent": "Error", "message": str(e), "data": {}})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------- static frontend
if os.path.isdir(_FRONTEND):
    app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_FRONTEND, "index.html"))
else:  # pragma: no cover
    @app.get("/")
    def index_missing():
        return JSONResponse({"error": "frontend not built"}, status_code=500)
