"""
Ingestion Agent.

Parses an unstructured distress report / news flash / field message into a
structured DisasterIncident. Uses Claude when available for robust extraction,
otherwise a transparent keyword/heuristic extractor so it always works.

UNDAC mapping: F.1 Information Management — turning raw inbound information into
structured, shareable data.
"""
from __future__ import annotations
import re
from typing import Optional

from ..models import DisasterIncident, GeoPoint
from ..data.hazard_kb import get_hazard_profile
from .. import llm
from ..skills_geo import get_coordinates

_TYPE_KEYWORDS = {
    "Earthquake": ["earthquake", "quake", "seismic", "tremor", "aftershock"],
    "Tsunami": ["tsunami", "tidal wave"],
    "Tropical Cyclone": ["cyclone", "hurricane", "typhoon", "storm surge"],
    "Flood": ["flood", "flooding", "inundat", "overflow", "deluge"],
    "Volcano": ["volcano", "volcanic", "eruption", "lava", "ashfall"],
    "Wildfire": ["wildfire", "bushfire", "forest fire", "blaze"],
    "Drought": ["drought", "famine", "water scarcity", "crop failure"],
}

_NEED_KEYWORDS = {
    "medics": ["medic", "injured", "casualt", "wounded", "trauma", "doctor", "hospital"],
    "water": ["water", "thirst", "dehydrat", "drinking"],
    "food_rations": ["food", "hungry", "starv", "ration", "nutrition"],
    "tents": ["shelter", "homeless", "tent", "displaced", "roof"],
    "rescue_boats": ["boat", "stranded", "trapped by water", "submerged"],
    "rescue_teams": ["trapped", "buried", "collapse", "search and rescue", "usar"],
    "ambulances": ["ambulance", "evacuat"],
    "helicopters": ["helicopter", "airlift", "cut off", "isolated"],
    "generators": ["power", "electricity", "blackout", "generator"],
    "masks": ["smoke", "ash", "respirat", "air quality"],
}


def _detect_type(text: str) -> str:
    low = text.lower()
    for dtype, kws in _TYPE_KEYWORDS.items():
        if any(k in low for k in kws):
            return dtype
    return "Unknown"


def _detect_needs(text: str) -> list[str]:
    low = text.lower()
    needs = [item for item, kws in _NEED_KEYWORDS.items() if any(k in low for k in kws)]
    return needs


def _extract_number(text: str, near_words: list[str]) -> Optional[int]:
    """Find the number most tightly associated with the given keywords, or None
    if the report states no such figure (we never invent one).

    Scores each number by the distance to the nearest keyword (closer = better),
    so "5000 affected and 200 injured" yields 200 for casualty words and 5000
    for affected words."""
    low = text.lower()
    best_n, best_dist = None, 10 ** 9
    for m in re.finditer(r"(\d[\d,]{0,11})\s*(\+|plus)?", low):
        try:
            n = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        window_start, window_end = max(0, m.start() - 25), m.end() + 25
        for w in near_words:
            idx = low.find(w, window_start, window_end)
            if idx != -1:
                dist = min(abs(idx - m.start()), abs(idx - m.end()))
                if dist < best_dist:
                    best_dist, best_n = dist, n
    return best_n


def _detect_location(text: str) -> str:
    # Look for "in/near/at/hit/struck <Place>", capping at a sentence boundary
    m = re.search(
        r"\b(?:in|near|at|hit|struck|impact(?:ing|ed)?)\s+"
        r"([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,3})",
        text,
    )
    if m:
        return m.group(1).strip(" .,")
    return "Unknown"


def run_ingestion_agent(raw_report: str, emit=None) -> DisasterIncident:
    def say(msg: str):
        if emit:
            emit("Ingestion", msg)

    say("Parsing inbound report and structuring incident data…")

    # --- LLM path -----------------------------------------------------------
    data = llm.complete_json(
        system=(
            "You are the Ingestion cell of a UN UNDAC disaster-coordination team. "
            "Extract structured incident data from a raw field report."
        ),
        user=(
            "From this report extract JSON with keys: disaster_type (one of Earthquake, "
            "Tsunami, Tropical Cyclone, Flood, Volcano, Wildfire, Drought, Unknown), "
            "location (place name), estimated_affected (int), estimated_casualties (int), "
            "specific_needs (array from: medics, water, food_rations, tents, rescue_boats, "
            "rescue_teams, ambulances, helicopters, generators, masks).\n\nREPORT:\n"
            + raw_report
        ),
        max_tokens=600,
    )

    def _opt_int(v):
        try:
            return int(v) if v not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            return None

    if data:
        say("Claude structured-extraction succeeded.")
        dtype = data.get("disaster_type") or _detect_type(raw_report)
        location = data.get("location") or _detect_location(raw_report)
        needs = data.get("specific_needs") or _detect_needs(raw_report)
        # only keep figures the report actually states; None = unknown
        affected = _opt_int(data.get("estimated_affected")) or _extract_number(
            raw_report, ["affect", "displaced", "people", "resident", "homeless"])
        casualties = _opt_int(data.get("estimated_casualties")) or _extract_number(
            raw_report, ["injur", "casualt", "dead", "kill", "wounded"])
    else:
        say("No LLM key — using deterministic keyword extractor.")
        dtype = _detect_type(raw_report)
        location = _detect_location(raw_report)
        needs = _detect_needs(raw_report)
        casualties = _extract_number(raw_report, ["injur", "casualt", "dead", "kill", "wounded"])
        affected = _extract_number(raw_report, ["affect", "displaced", "people", "resident", "homeless"])

    # If hazard known but needs empty, seed with hazard-typical key resources
    if not needs and dtype != "Unknown":
        prof = get_hazard_profile(dtype)
        needs = prof["key_resources"][:3]
        say(f"No explicit needs found — seeding hazard-typical needs for {dtype}.")

    coords = GeoPoint()
    if location and location != "Unknown":
        latlon = get_coordinates(location)
        if latlon:
            coords = GeoPoint(lat=latlon[0], lon=latlon[1])
            say(f"Geocoded '{location}' → ({coords.lat:.3f}, {coords.lon:.3f}).")

    incident = DisasterIncident(
        disaster_type=dtype,
        location=location,
        coordinates=coords,
        estimated_affected=affected,
        estimated_casualties=casualties,
        specific_needs=needs,
        raw_report=raw_report,
    )
    say(f"Structured: {dtype} @ {location} · needs={needs} · casualties={casualties}")
    return incident
