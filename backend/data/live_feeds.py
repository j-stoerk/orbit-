"""
Live disaster data feeds — all free, keyless, public APIs so the platform is
"real, live and usable for everyone" out of the box.

  * USGS      — global earthquakes (GeoJSON)            earthquake.usgs.gov
  * GDACS     — Global Disaster Alert & Coordination    gdacs.org
  * ReliefWeb — OCHA situation reports & disasters       reliefweb.int

Each function returns a normalised list of `dict` events with at least:
    id, title, type, lat, lon, severity, magnitude, time, source, url
so the frontend globe can plot them uniformly.
"""

from __future__ import annotations
import os
import time
import datetime as _dt
from typing import Dict, Any, List

import requests

_TIMEOUT = 12
_HEADERS = {"User-Agent": "UNDAC-CrisisCoordinator/2.0 (humanitarian coordination platform)"}

# very small TTL cache so we don't hammer upstream APIs while the UI polls
_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 60  # seconds


def _cached(key: str):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["t"] < _CACHE_TTL):
        return entry["v"]
    return None


def _store(key: str, value):
    _CACHE[key] = {"t": time.time(), "v": value}
    return value


def _alert_to_severity(level: str) -> str:
    return {"red": "Critical", "orange": "High", "green": "Moderate"}.get(
        (level or "").lower(), "Moderate"
    )


def _mag_to_severity(mag: float) -> str:
    if mag >= 7.0:
        return "Critical"
    if mag >= 6.0:
        return "High"
    if mag >= 4.5:
        return "Moderate"
    return "Low"


def get_usgs_earthquakes(min_magnitude: float = 4.0, window: str = "all_day") -> List[Dict[str, Any]]:
    """Recent earthquakes from USGS. window: all_hour|all_day|all_week."""
    ck = f"usgs:{min_magnitude}:{window}"
    if (c := _cached(ck)) is not None:
        return c
    url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{window}.geojson"
    out: List[Dict[str, Any]] = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        for f in resp.json().get("features", []):
            p = f.get("properties", {})
            g = f.get("geometry", {})
            mag = p.get("mag") or 0
            if mag < min_magnitude:
                continue
            coords = g.get("coordinates", [None, None, None])
            # PAGER alert (green/yellow/orange/red) is a real impact signal; when
            # present it outranks raw magnitude for severity.
            pager = (p.get("alert") or "").capitalize()
            sev = {"Red": "Critical", "Orange": "High", "Yellow": "Moderate",
                   "Green": "Low"}.get(pager) or _mag_to_severity(mag)
            out.append({
                "id": f.get("id"),
                "title": p.get("place") or "Earthquake",
                "type": "Earthquake",
                "lat": coords[1],
                "lon": coords[0],
                "depth_km": coords[2],
                "magnitude": mag,
                "severity": sev,
                "pager_alert": p.get("alert"),
                "mmi": p.get("mmi"),
                "felt": p.get("felt"),
                "tsunami": p.get("tsunami"),
                "detail": p.get("detail"),   # event-detail GeoJSON (for PAGER exposure)
                "time": _dt.datetime.utcfromtimestamp((p.get("time") or 0) / 1000).isoformat() + "Z",
                "source": "USGS",
                "url": p.get("url"),
            })
        out.sort(key=lambda e: e["magnitude"], reverse=True)
    except Exception as e:  # pragma: no cover - network
        out = [{"error": f"USGS feed unavailable: {e}"}]
    return _store(ck, out)


def get_gdacs_alerts() -> List[Dict[str, Any]]:
    """Active GDACS alerts (Orange/Red), normalised."""
    ck = "gdacs"
    if (c := _cached(ck)) is not None:
        return c
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP?alertlevel=Orange;Red"
    type_map = {"EQ": "Earthquake", "TC": "Tropical Cyclone", "FL": "Flood",
                "VO": "Volcano", "DR": "Drought", "WF": "Wildfire", "TS": "Tsunami"}
    out: List[Dict[str, Any]] = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        for f in resp.json().get("features", []):
            p = f.get("properties", {})
            g = f.get("geometry", {})
            coords = g.get("coordinates", [None, None])
            etype = type_map.get(p.get("eventtype", ""), p.get("eventtype", "Hazard"))
            sd = p.get("severitydata", {}) or {}
            out.append({
                "id": f"gdacs-{p.get('eventtype')}-{p.get('eventid')}",
                "title": p.get("name") or p.get("htmldescription") or etype,
                "type": etype,
                "lat": coords[1] if len(coords) > 1 else None,
                "lon": coords[0] if len(coords) > 0 else None,
                "magnitude": sd.get("severity"),
                "severity": _alert_to_severity(p.get("alertlevel")),
                "alertlevel": p.get("alertlevel"),
                "severity_text": sd.get("severitytext"),
                "gdacs_eventtype": p.get("eventtype"),
                "gdacs_eventid": p.get("eventid"),
                "country": p.get("country"),
                "time": p.get("fromdate"),
                "source": "GDACS",
                "url": p.get("url", {}).get("report") if isinstance(p.get("url"), dict) else None,
            })
    except Exception as e:  # pragma: no cover - network
        out = [{"error": f"GDACS feed unavailable: {e}"}]
    return _store(ck, out)


def get_reliefweb_disasters(limit: int = 20) -> List[Dict[str, Any]]:
    """Current disasters tracked by OCHA ReliefWeb (API v2). Coordinates are
    resolved from the primary country name via the geocoding skill, since the
    public v2 endpoint does not expose country centroids in the list profile."""
    from ..skills_geo import get_coordinates  # local import to avoid cycle

    ck = f"reliefweb:{limit}"
    if (c := _cached(ck)) is not None:
        return c
    # ReliefWeb v2 requires a registered appname; set RELIEFWEB_APPNAME to enable.
    appname = os.environ.get("RELIEFWEB_APPNAME", "undac-crisis-coordinator")
    url = f"https://api.reliefweb.int/v2/disasters?appname={appname}"
    body = {
        "profile": "list",
        "preset": "latest",
        "limit": limit,
        "fields": {"include": ["name", "status", "primary_country.name",
                                 "type.name", "date.created"]},
    }
    out: List[Dict[str, Any]] = []
    try:
        resp = requests.post(url, headers=_HEADERS, json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            f = item.get("fields", {})
            pc = f.get("primary_country", {}) or {}
            types = f.get("type", [])
            country = pc.get("name")
            latlon = get_coordinates(country) if country else None
            out.append({
                "id": f"rw-{item.get('id')}",
                "title": f.get("name"),
                "type": (types[0]["name"] if types else "Disaster"),
                "lat": latlon[0] if latlon else None,
                "lon": latlon[1] if latlon else None,
                "severity": "High" if f.get("status") == "ongoing" else "Moderate",
                "country": country,
                "status": f.get("status"),
                "time": (f.get("date", {}) or {}).get("created"),
                "source": "ReliefWeb",
                "url": item.get("href"),
            })
    except Exception as e:  # pragma: no cover - network
        out = [{"error": f"ReliefWeb feed unavailable: {e}"}]
    return _store(ck, out)


def get_eonet_events(limit: int = 50) -> List[Dict[str, Any]]:
    """NASA EONET — open natural events (wildfires, severe storms, volcanoes,
    etc.). Keyless and global; complements USGS/GDACS coverage."""
    ck = f"eonet:{limit}"
    if (c := _cached(ck)) is not None:
        return c
    url = f"https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit={limit}"
    cat_map = {
        "wildfires": ("Wildfire", "High"), "severeStorms": ("Tropical Cyclone", "High"),
        "volcanoes": ("Volcano", "High"), "floods": ("Flood", "High"),
        "drought": ("Drought", "Moderate"), "earthquakes": ("Earthquake", "High"),
        "landslides": ("Landslide", "High"), "seaLakeIce": ("Sea/Lake Ice", "Low"),
        "snow": ("Snow", "Moderate"), "dustHaze": ("Dust/Haze", "Moderate"),
        "manmade": ("Man-made", "Moderate"), "waterColor": ("Water", "Low"),
        "temperatureExtremes": ("Extreme Temp", "Moderate"),
    }
    out: List[Dict[str, Any]] = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        for ev in resp.json().get("events", []):
            cats = ev.get("categories", [])
            cat_id = cats[0]["id"] if cats else ""
            etype, sev = cat_map.get(cat_id, ("Hazard", "Moderate"))
            geoms = ev.get("geometry", [])
            if not geoms:
                continue
            g = geoms[-1]  # most recent geometry
            coords = g.get("coordinates")
            # polygons -> take first vertex; points -> use directly
            while isinstance(coords, list) and coords and isinstance(coords[0], list):
                coords = coords[0]
            if not (isinstance(coords, list) and len(coords) >= 2):
                continue
            out.append({
                "id": f"eonet-{ev.get('id')}",
                "title": ev.get("title"),
                "type": etype,
                "lat": coords[1],
                "lon": coords[0],
                "severity": sev,
                "time": g.get("date"),
                "source": "EONET",
                "url": (ev.get("sources", [{}])[0].get("url") if ev.get("sources") else ev.get("link")),
            })
    except Exception as e:  # pragma: no cover - network
        out = [{"error": f"EONET feed unavailable: {e}"}]
    return _store(ck, out)


def get_all_events(min_magnitude: float = 4.5) -> List[Dict[str, Any]]:
    """Aggregate all live feeds into one normalised list for the globe."""
    events: List[Dict[str, Any]] = []
    for fn in (lambda: get_usgs_earthquakes(min_magnitude),
               get_gdacs_alerts,
               lambda: get_eonet_events(50),
               lambda: get_reliefweb_disasters(15)):
        try:
            for e in fn():
                if "error" not in e and e.get("lat") is not None and e.get("lon") is not None:
                    events.append(e)
        except Exception:
            continue
    return events
