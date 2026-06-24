"""
Assessment & Analysis Agent (MIRA) — grounded edition.

Severity and impact figures are derived from REAL sources where available:
  * USGS PAGER / GDACS alert levels and reported impacts (passed in via
    ``exposure``), and
  * any figures explicitly stated in the inbound report.

When neither exists, figures are returned as ``None`` ("not estimated") and the
severity is flagged *preliminary* — the agent never invents population numbers.

UNDAC mapping: F.2 Assessment and Analysis; Section K Hazard Impact Summaries.
"""
from __future__ import annotations
from typing import Optional, Dict, Any

from ..models import DisasterIncident, Assessment, SectorNeed
from ..data.hazard_kb import get_hazard_profile

# Alert level → severity (PAGER lower-case, GDACS capitalised)
_ALERT_SEV = {
    "red": "Critical", "orange": "High", "yellow": "Moderate", "green": "Low",
}
_ALERT_INDEX = {"red": 92, "orange": 72, "yellow": 48, "green": 22}


def _sev_from_casualties(n: int) -> tuple[str, int]:
    if n >= 1000:
        return "Critical", 95
    if n >= 100:
        return "Critical", 82
    if n >= 10:
        return "High", 60
    if n >= 1:
        return "Moderate", 40
    return "Low", 20


def run_assessment_agent(incident: DisasterIncident,
                         exposure: Optional[Dict[str, Any]] = None,
                         emit=None) -> Assessment:
    def say(msg):
        if emit:
            emit("Assessment", msg)

    exposure = exposure or {}
    profile = get_hazard_profile(incident.disaster_type)
    say(f"Assessing {incident.disaster_type} using hazard profile {profile['handbook_ref']}.")

    # ---- figures: real exposure first, then explicit report, else unknown ----
    affected = exposure.get("affected")
    affected_label = exposure.get("affected_label", "")
    if affected is None and incident.estimated_affected is not None:
        affected = incident.estimated_affected
        affected_label = "stated in report"

    fatalities = exposure.get("fatalities")
    fatalities_label = exposure.get("fatalities_label", "")
    if fatalities is None and incident.estimated_casualties is not None:
        fatalities = incident.estimated_casualties
        fatalities_label = "stated in report"

    displaced = exposure.get("displaced")
    displaced_label = exposure.get("displaced_label", "")

    alert = exposure.get("alert_level")
    sources = list(exposure.get("sources", []))

    # ---- severity: grounded in the strongest available signal ----
    if alert:
        a = alert.lower()
        severity = _ALERT_SEV.get(a, "Moderate")
        index = _ALERT_INDEX.get(a, 45)
        src = (sources[0]["name"] if sources else "official")
        basis = f"{src} alert level: {alert.capitalize()}"
        if exposure.get("severity_text"):
            basis += f" — {exposure['severity_text']}"
        say(f"Severity grounded in {basis}.")
    elif fatalities is not None and fatalities > 0:
        severity, index = _sev_from_casualties(fatalities)
        basis = f"reported casualties ({fatalities:,})"
        say(f"Severity from {basis}.")
    elif affected is not None and affected > 0:
        if affected >= 100000:
            severity, index = "High", 60
        elif affected >= 10000:
            severity, index = "Moderate", 45
        else:
            severity, index = "Moderate", 35
        basis = f"reported affected population ({affected:,})"
        say(f"Severity from {basis}.")
    else:
        # No impact data yet — preliminary rating from hazard type only
        preliminary = {"Earthquake": ("High", 55), "Tsunami": ("High", 58),
                       "Tropical Cyclone": ("High", 55)}.get(
            incident.disaster_type, ("Moderate", 40))
        severity, index = preliminary
        basis = "preliminary — no exposure data yet; rated from hazard type"
        say("No real exposure data — issuing a PRELIMINARY rating from hazard type only.")

    # ---- sectors / actions from the handbook KB (guidance, cited) ----
    sector_needs = []
    for rank, sector in enumerate(profile["priority_sectors"]):
        priority = "Critical" if (rank == 0 and severity in ("Critical", "High")) \
            else ("High" if rank <= 1 else "Moderate")
        sector_needs.append(SectorNeed(
            sector=sector, priority=priority,
            rationale=f"{sector} prioritised for {incident.disaster_type} response.",
            indicators=profile["assessment_indicators"][:3],
        ))
    sources.append({"name": f"UNDAC Handbook {profile['handbook_ref']} (hazard guidance)",
                    "url": "https://www.unocha.org/our-work/coordination/un-disaster-assessment-and-coordination-undac"})

    assessment = Assessment(
        severity_score=severity,
        severity_index=index,
        severity_basis=basis,
        urgency_reasoning=basis,
        affected_population=affected,
        affected_label=affected_label,
        displaced_estimate=displaced,
        displaced_label=displaced_label,
        fatalities_estimate=fatalities,
        fatalities_label=fatalities_label,
        alert_level=alert,
        exposure_available=bool(exposure.get("available")),
        data_sources=sources,
        secondary_hazards=profile["secondary_hazards"],
        sector_needs=sector_needs,
        priority_actions=profile["priority_actions"],
        hazard_ref=profile["handbook_ref"],
        golden_hours=profile.get("golden_hours", 72),
    )
    have = [n for n, v in [("affected", affected), ("fatalities", fatalities),
                           ("displaced", displaced)] if v is not None]
    say(f"Assessment: {severity}. Real figures: {', '.join(have) if have else 'none (not estimated)'}.")
    return assessment
