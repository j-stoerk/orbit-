"""
Coordination Agent (OSOCC).

Stands up the On-Site Operations Coordination Centre picture: which clusters
lead, a 3W matrix (Who does What, Where), identified coordination gaps, and a
tasking list. This is the heart of UNDAC's value-add — coordinating, not doing.

UNDAC mapping: D. The OSOCC Concept; G.6 Inter-Cluster/Sector Coordination;
F.1 the 3W information product.
"""
from __future__ import annotations

from ..models import Assessment, DisasterIncident, CoordinationPlan, ThreeWEntry

# Standard IASC cluster lead agencies (handbook A.3 / cluster system)
CLUSTER_LEADS = {
    "Health": "WHO",
    "WASH": "UNICEF",
    "Shelter/NFI": "IFRC / UNHCR",
    "Food Security": "WFP & FAO",
    "Protection": "UNHCR",
    "Logistics": "WFP (Logistics Cluster)",
    "Emergency Telecommunications": "WFP (ETC)",
    "Education": "UNICEF & Save the Children",
    "Early Recovery": "UNDP",
    "Camp Coordination": "IOM / UNHCR",
    "Nutrition": "UNICEF",
}

# Typical first activities per sector for the 3W matrix
SECTOR_ACTIVITIES = {
    "Health": "Field medical teams (EMT) & trauma triage",
    "WASH": "Safe water supply & sanitation",
    "Shelter/NFI": "Emergency shelter & non-food item distribution",
    "Food Security": "Emergency food / cash assistance",
    "Protection": "Protection monitoring & family reunification",
    "Logistics": "Access clearance & relief supply chain",
    "Emergency Telecommunications": "Restore connectivity for responders",
    "Education": "Temporary learning spaces",
    "Early Recovery": "Debris management & livelihoods",
}


def run_coordination_agent(incident: DisasterIncident, assessment: Assessment,
                           emit=None) -> CoordinationPlan:
    def say(msg):
        if emit:
            emit("Coordination", msg)

    place = incident.location or "the affected area"
    say(f"Activating OSOCC coordination for {place}.")

    lead_clusters = [sn.sector for sn in assessment.sector_needs]
    say(f"Lead clusters engaged: {', '.join(lead_clusters)}.")

    hazard_ref = assessment.hazard_ref
    three_w = []
    for sn in assessment.sector_needs:
        lead = CLUSTER_LEADS.get(sn.sector, "National authorities")
        activity = SECTOR_ACTIVITIES.get(sn.sector, f"{sn.sector} response")
        status = "Proposed"
        # evidence-first rationale: WHY this cluster is recommended
        rationale = (f"{sn.sector} is a {sn.priority.lower()}-priority sector for "
                     f"{incident.disaster_type} (UNDAC {hazard_ref}); "
                     f"severity {assessment.severity_score} per {assessment.severity_basis}.")
        three_w.append(ThreeWEntry(
            who=lead, what=activity, where=place, sector=sn.sector, status=status,
            rationale=rationale,
        ))

    # Coordination gaps — sectors that are high priority but commonly under-resourced
    gaps = []
    common_gap_sectors = {"Protection", "Emergency Telecommunications", "Early Recovery", "Logistics"}
    for sn in assessment.sector_needs:
        if sn.sector in common_gap_sectors and sn.priority in ("Critical", "High"):
            gaps.append(f"{sn.sector}: lead capacity likely insufficient — request surge support.")
    if assessment.severity_score == "Critical":
        gaps.append("Inter-cluster information flow: establish IM Working Group & shared 3W.")
    if not gaps:
        gaps.append("No critical coordination gaps detected at this stage.")

    tasking = [
        f"Establish OSOCC / Reception & Departure Centre (RDC) near {place}.",
        "Convene first inter-cluster coordination meeting within 6 hours.",
        "Publish initial 3W and share via Virtual OSOCC (VOSOCC).",
        f"Liaise with national authorities (LEMA/NDMA) on {incident.disaster_type} response.",
    ]
    if assessment.golden_hours and assessment.golden_hours <= 72:
        tasking.insert(0, f"Prioritise life-saving actions within the {assessment.golden_hours}h window.")

    say(f"3W matrix built with {len(three_w)} entries; {len(gaps)} coordination gap(s) flagged.")
    return CoordinationPlan(
        osocc_activated=True,
        lead_clusters=lead_clusters,
        three_w=three_w,
        coordination_gaps=gaps,
        tasking=tasking,
    )
