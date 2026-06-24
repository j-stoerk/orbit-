"""
Explainability & uncertainty engine.

Turns the raw signals into:
  * an **evidence ledger** (every figure / recommendation traces to sources),
  * a **confidence** rating that is SEPARATE from severity (a loud single report
    is "Unverified"; a multi-source-confirmed event is "Confirmed"), and
  * a MIRA-style list of **unanswered questions** (what is still uncertain).

This is what lets an operator answer, in seconds: what happened, who owns what
next, and what is still uncertain.
"""
from __future__ import annotations
import math
from typing import List, Dict, Any, Optional, Tuple

from .models import (DisasterIncident, Assessment, Evidence, Confidence,
                     OpenQuestion, CoordinationPlan)
from .data.hazard_kb import get_hazard_profile


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R, p = 6371.0, math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def build_evidence(incident: DisasterIncident, assessment: Assessment,
                   exposure: Optional[Dict[str, Any]], all_events: List[Dict[str, Any]],
                   media: Dict[str, Any], context: Dict[str, Any]
                   ) -> Tuple[List[Evidence], List[str]]:
    """Assemble the evidence ledger; also return the list of corroborating
    source names used for confidence."""
    ev: List[Evidence] = []
    corroborating: List[str] = []
    coords = incident.coordinates

    # 1) primary authoritative exposure (USGS PAGER / GDACS)
    if exposure and exposure.get("available"):
        for s in exposure.get("sources", []):
            name = s.get("name", "")
            if name and "Handbook" not in name:
                corroborating.append(name)
        alert = exposure.get("alert_level")
        if alert:
            ev.append(Evidence(source=exposure["sources"][0]["name"] if exposure.get("sources") else "Feed",
                               kind="feed", statement=f"Official alert level: {alert.capitalize()}"
                               + (f" — {exposure['severity_text']}" if exposure.get("severity_text") else ""),
                               url=(exposure["sources"][0]["url"] if exposure.get("sources") else None)))
        if exposure.get("affected") is not None:
            ev.append(Evidence(source="USGS PAGER", kind="feed",
                               statement=f"Exposure: {exposure.get('affected_label') or str(exposure['affected'])}",
                               url=(exposure["sources"][0]["url"] if exposure.get("sources") else None)))
        if exposure.get("reported"):
            for k in ("fatalities", "displaced", "affected"):
                if exposure.get(k) is not None:
                    ev.append(Evidence(source="GDACS", kind="feed",
                                       statement=f"Reported {k}: {exposure[k]:,}"))

    # 2) corroborating independent feeds near the location
    if coords and coords.lat is not None:
        seen_src = set(corroborating)
        for e in all_events:
            elat, elon = e.get("lat"), e.get("lon")
            if not isinstance(elat, (int, float)) or not isinstance(elon, (int, float)):
                continue
            if e.get("source") in seen_src:
                continue
            d = _haversine(coords.lat, coords.lon, elat, elon)
            same_type = (e.get("type") == incident.disaster_type)
            if d <= 200 and same_type:
                seen_src.add(e.get("source"))
                corroborating.append(e.get("source"))
                ev.append(Evidence(source=e["source"], kind="feed",
                                   statement=f"Independent {e['source']} report of {e.get('type')} "
                                             f"~{int(d)} km away: {(e.get('title') or '')[:70]}",
                                   url=e.get("url"), time=e.get("time")))

    # 3) news corroboration
    news = (media or {}).get("news", [])
    for a in news[:4]:
        ev.append(Evidence(source=a.get("source", "News"), kind="news",
                           statement=a.get("title", ""), url=a.get("url"), time=a.get("time")))
    if news:
        corroborating.append(f"{len(news)} news articles")

    # 4) social signal
    social = (media or {}).get("social", [])
    for p in social[:2]:
        ev.append(Evidence(source="Mastodon", kind="social",
                           statement=(p.get("text") or "")[:140], url=p.get("url"), time=p.get("time")))

    # 5) context evidence (operating environment / assets)
    if context and context.get("available"):
        wx = context.get("weather")
        if wx:
            ev.append(Evidence(source="Open-Meteo", kind="context",
                               statement=f"Operating conditions: {wx['conditions']}, "
                                         f"{wx['temperature_c']}°C, wind {wx['wind_kmh']} km/h, "
                                         f"precip {wx['precipitation_mm']} mm"))
        hosp = context.get("hospitals", [])
        if hosp:
            ev.append(Evidence(source="OpenStreetMap", kind="context",
                               statement=f"{len(hosp)} hospital(s) within 60 km; nearest "
                                         f"'{hosp[0]['name']}' at {hosp[0]['distance_km']} km"))
        air = context.get("airports", [])
        if air:
            ev.append(Evidence(source="OpenStreetMap", kind="context",
                               statement=f"Nearest aerodrome for relief logistics: "
                                         f"'{air[0]['name']}' at {air[0]['distance_km']} km"))
        sat = context.get("satellite")
        if sat:
            ev.append(Evidence(source=sat["source"], kind="context",
                               statement=f"Near-real-time {sat['layer']} satellite imagery "
                                         f"of the area ({sat['date']}) available.",
                               url=sat.get("worldview"), time=sat.get("date")))
        at = context.get("air_traffic")
        if at and at.get("count"):
            ev.append(Evidence(source="OpenSky", kind="context",
                               statement=f"{at['count']} aircraft currently tracked within ~150 km "
                                         f"({at['airborne']} airborne) — airspace is active."))
        fires = context.get("fires")
        if fires and fires.get("count"):
            ev.append(Evidence(source=fires["source"], kind="feed",
                               statement=f"{fires['count']} active fire detections within ~150 km "
                                         f"(nearest {fires.get('nearest_km')} km, max FRP {fires.get('max_frp')} MW)."))
            # active fires independently corroborate a wildfire event
            if incident.disaster_type == "Wildfire":
                corroborating.append("NASA FIRMS")
        aq = context.get("air_quality")
        if aq and aq.get("pm25") is not None:
            ev.append(Evidence(source="OpenAQ", kind="context",
                               statement=f"Ground air quality near site: PM2.5 {aq['pm25']} µg/m³ "
                                         f"({aq['band']}) at {aq.get('location','monitor')}."))
        sm = context.get("shakemap")
        if sm:
            ev.append(Evidence(source="USGS ShakeMap", kind="feed",
                               statement="Modelled ground shaking-intensity map (ShakeMap) available.",
                               url=sm.get("url")))
        radar = context.get("radar")
        if radar:
            ev.append(Evidence(source="RainViewer", kind="context",
                               statement="Live precipitation-radar tile covering the site.",
                               url=radar.get("radar_url"), time=radar.get("time")))
        ves = context.get("vessels")
        if ves and ves.get("count"):
            ev.append(Evidence(source="VesselAPI", kind="context",
                               statement=f"{ves['count']} vessels (AIS) within ~80 km "
                                         f"({ves['moving']} under way); nearest '{ves['nearest']['name']}' "
                                         f"at {ves['nearest']['dist_km']} km — potential maritime assets."))
        ports = context.get("ports")
        if ports:
            ev.append(Evidence(source="VesselAPI", kind="context",
                               statement=f"Nearest seaport for relief: '{ports[0]['name']}' "
                                         f"({ports[0]['distance_km']} km)."))
        conf = context.get("conflict")
        if conf and conf.get("available") and conf.get("events"):
            ev.append(Evidence(source="ACLED", kind="feed",
                               statement=f"{len(conf['events'])} recent conflict/unrest events within "
                                         f"~300 km — security context relevant to access & staff safety."))
    return ev, corroborating


def build_confidence(exposure: Optional[Dict[str, Any]], corroborating: List[str],
                     media: Dict[str, Any], has_explicit_report: bool) -> Confidence:
    score, reasons = 0, []
    feed_sources = [c for c in corroborating if not c.endswith("articles")]
    distinct_feeds = len(set(feed_sources))

    if exposure and exposure.get("available"):
        score += 45
        reasons.append("Authoritative feed (USGS PAGER / GDACS) reporting this event.")
    if distinct_feeds >= 2:
        score += 20
        reasons.append(f"{distinct_feeds} independent feeds corroborate the event.")
    elif distinct_feeds == 1 and not (exposure and exposure.get("available")):
        score += 15
        reasons.append("One feed source reporting the event.")

    n_news = len((media or {}).get("news", []))
    if n_news:
        score += min(20, n_news * 4)
        reasons.append(f"{n_news} news articles reference the event.")
    n_social = len((media or {}).get("social", []))
    if n_social:
        score += min(8, n_social * 2)
        reasons.append(f"{n_social} social posts reference the hazard.")

    if exposure and exposure.get("reported"):
        score += 12
        reasons.append("Authorities have reported ground-truth impact figures (GDACS sendai).")

    if score == 0 and has_explicit_report:
        reasons.append("Single unverified report; no independent corroboration yet.")

    score = max(0, min(100, score))
    level = "Confirmed" if score >= 70 else ("Probable" if score >= 40 else "Unverified")
    srcs = sorted(set(feed_sources)) + ([f"{n_news} news"] if n_news else []) + ([f"{n_social} social"] if n_social else [])
    return Confidence(level=level, score=score, corroborating_sources=srcs, reasons=reasons)


def build_open_questions(incident: DisasterIncident, assessment: Assessment,
                         context: Dict[str, Any]) -> List[OpenQuestion]:
    """MIRA-style: which assessment indicators do we still lack data for?"""
    profile = get_hazard_profile(incident.disaster_type)
    qs: List[OpenQuestion] = []

    if assessment.affected_population is None:
        qs.append(OpenQuestion(question="How many people are affected?", category="impact",
                               why="No exposure figure from feeds or report; drives the entire response scale."))
    if assessment.displaced_estimate is None:
        qs.append(OpenQuestion(question="How many people are displaced / need shelter?", category="impact",
                               why="Determines shelter, NFI and camp-coordination requirements."))
    if assessment.fatalities_estimate is None and not assessment.fatalities_label:
        qs.append(OpenQuestion(question="What are the casualty figures?", category="impact",
                               why="Drives medical surge and search-and-rescue prioritisation."))

    # hazard-specific indicators not yet covered by data
    covered = {"affected", "population", "displaced", "casualt", "death", "fatal"}
    for ind in profile["assessment_indicators"]:
        low = ind.lower()
        if any(c in low for c in covered):
            continue
        qs.append(OpenQuestion(question=f"{ind}?", category="sector",
                               why=f"Key {incident.disaster_type} assessment indicator (UNDAC {profile['handbook_ref']})."))

    # access / capacity
    if not (context and context.get("airports")):
        qs.append(OpenQuestion(question="Is there a functioning aerodrome / port for relief access?",
                               category="access", why="Determines feasible logistics corridors."))
    else:
        # we know an airport exists, but is it operational?
        qs.append(OpenQuestion(question=f"Is {context['airports'][0]['name']} operational and open to relief flights?",
                               category="access", why="Nearest aerodrome identified; operability not confirmed."))
    if not (context and context.get("hospitals")):
        qs.append(OpenQuestion(question="What is the local medical surge capacity?", category="capacity",
                               why="No hospitals located near the site; medical response may need to be imported."))

    qs.append(OpenQuestion(question="What is the national/local authority response capacity and lead?",
                           category="capacity",
                           why="UNDAC supports, it does not replace, national coordination (LEMA/NDMA)."))
    return qs[:9]
