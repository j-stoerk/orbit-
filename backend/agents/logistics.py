"""
Logistics Agent — registry-backed, honest edition.

Reads the **real resource registry** (located, user-owned stock), lists what is
relevant to the incident with its actual availability and locations, and — only
when a real affected-population figure exists — quantifies demand and computes
the gap. With no population figure it does NOT invent quantities; it simply
surfaces available stock and marks demand "pending assessment".

On commit (after HITL approval) it deducts allocations from the registry.

UNDAC mapping: G.11 Disaster logistics; H.2 Logistics support.
"""
from __future__ import annotations
from typing import Dict

from ..models import DisasterIncident, Assessment, LogisticsPlan, ResourceLine
from ..data.hazard_kb import get_hazard_profile
from ..resources import STORE as RESOURCES

# Planning demand: base units per 1,000 affected people, scaled by severity
_DEMAND_PER_1000 = {
    "water": 50, "food_rations": 40, "tents": 20, "medics": 3, "ambulances": 1,
    "rescue_boats": 2, "rescue_teams": 2, "helicopters": 1, "generators": 2,
    "masks": 60, "water_purification": 5, "tarpaulins": 25, "buses": 2,
    "body_bags": 5, "cash_transfers": 30,
}
_SEVERITY_MULT = {"Critical": 1.5, "High": 1.1, "Moderate": 0.7, "Low": 0.4}


def run_logistics_agent(incident: DisasterIncident, assessment: Assessment,
                        commit: bool = False, emit=None) -> LogisticsPlan:
    def say(msg):
        if emit:
            emit("Logistics", msg)

    profile = get_hazard_profile(incident.disaster_type)
    relevant = list(dict.fromkeys((incident.specific_needs or []) + profile["key_resources"]))

    # real affected basis (None if unknown — we do not invent demand)
    basis = assessment.affected_population
    if basis is None:
        basis = assessment.displaced_estimate
    mult = _SEVERITY_MULT.get(assessment.severity_score, 1.0)

    if basis is not None:
        say(f"Quantifying demand for {len(relevant)} resource types against "
            f"{basis:,} affected (severity {assessment.severity_score}).")
    else:
        say("No population figure available — listing real available stock by type; "
            "demand quantities pending assessment.")

    totals = RESOURCES.totals_by_type()
    lines, unmet, total_gap = [], [], 0
    for rtype in sorted(relevant):
        locs_records = RESOURCES.locations_for(rtype)
        available = totals.get(rtype, 0)
        locations = sorted({r.location for r in locs_records if r.location})
        label = (locs_records[0].label if locs_records else rtype.replace("_", " ").title())
        unit = (locs_records[0].unit if locs_records else "units")

        if basis is not None:
            per_k = _DEMAND_PER_1000.get(rtype, 10)
            requested = max(1, int(round((basis / 1000.0) * per_k * mult)))
            allocated = min(available, requested)
            gap = requested - allocated
            status = "Filled" if gap == 0 else ("Partial" if allocated > 0 else "Unmet")
            if gap > 0:
                total_gap += 1
                unmet.append((rtype, label, requested, allocated, gap))
            if commit and allocated > 0:
                RESOURCES.consume(rtype, allocated)
        else:
            requested, allocated, gap, status = None, 0, None, "In stock"

        lines.append(ResourceLine(
            item=rtype, label=label, unit=unit, available=available, locations=locations,
            requested=requested, allocated=allocated, gap=gap, status=status,
        ))

    if commit and basis is not None:
        say("Allocations committed — registry stock deducted at source locations.")

    procurement = [
        f"Procure/airlift {gap:,} {label.lower()} (have {alloc}, need {req})."
        for (_t, label, req, alloc, gap) in unmet
    ]
    if basis is None:
        summary = (f"{len(lines)} relevant resource types listed with real availability; "
                   "demand quantification pending a population figure.")
        procurement = ["Quantify needs once affected-population data is available."]
    elif not procurement:
        summary = f"All {len(lines)} requested resource types covered from current stock."
        procurement = ["All requested resources covered from current registry stock."]
    else:
        summary = (f"{len(lines) - len(unmet)}/{len(lines)} resource types fully met; "
                   f"{len(unmet)} require external procurement.")
    say(summary)

    return LogisticsPlan(
        lines=lines, total_gap_items=total_gap, summary=summary,
        procurement_recommendations=procurement,
    )
