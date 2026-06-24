"""
On-the-ground context for an incident location — real, keyless sources that
reduce uncertainty and surface concrete logistics/medical options:

  * Open-Meteo  — current weather & operating conditions at the site.
  * OSM Overpass — nearest hospitals (medical surge capacity) and aerodromes
                   (relief logistics access), with distances.

Used to answer "what is the operating environment?" and "what logistics/medical
assets are nearby?" — and to generate evidence + reduce open questions.
"""
from __future__ import annotations
import os
import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor
import time
import datetime as _dt
from typing import Dict, Any, List, Optional

import requests

_HEADERS = {"User-Agent": "ORBIT-CrisisCoordinator/1.0 (humanitarian coordination)"}
_TIMEOUT = 20
_CACHE: Dict[str, Any] = {}
_TTL = 600

_WEATHER_CODE = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
    96: "Thunderstorm w/ hail", 99: "Severe thunderstorm",
}


def _cached(k):
    e = _CACHE.get(k)
    return e["v"] if e and time.time() - e["t"] < _TTL else None


def _store(k, v):
    _CACHE[k] = {"t": time.time(), "v": v}
    return v


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def get_weather(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    ck = f"wx:{round(lat,2)}:{round(lon,2)}"
    if (c := _cached(ck)) is not None:
        return c
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", headers=_HEADERS, timeout=_TIMEOUT,
                         params={"latitude": lat, "longitude": lon,
                                 "current": "temperature_2m,precipitation,wind_speed_10m,weather_code"})
        r.raise_for_status()
        cur = r.json().get("current", {})
        out = {
            "temperature_c": cur.get("temperature_2m"),
            "precipitation_mm": cur.get("precipitation"),
            "wind_kmh": cur.get("wind_speed_10m"),
            "conditions": _WEATHER_CODE.get(cur.get("weather_code"), "—"),
            "time": cur.get("time"),
            "source": "Open-Meteo",
        }
        return _store(ck, out)
    except Exception:
        return None


def get_facilities(lat: float, lon: float) -> Dict[str, List[Dict[str, Any]]]:
    """Nearest hospitals (≤60 km) and aerodromes (≤250 km) from OSM."""
    ck = f"osm:{round(lat,2)}:{round(lon,2)}"
    if (c := _cached(ck)) is not None:
        return c
    q = (f'[out:json][timeout:25];('
         f'node["amenity"="hospital"](around:60000,{lat},{lon});'
         f'way["amenity"="hospital"](around:60000,{lat},{lon});'
         f'node["aeroway"="aerodrome"](around:250000,{lat},{lon});'
         f'way["aeroway"="aerodrome"](around:250000,{lat},{lon});'
         f');out center 60;')
    out = {"hospitals": [], "airports": []}
    try:
        r = requests.get("https://overpass-api.de/api/interpreter", headers=_HEADERS,
                         timeout=_TIMEOUT + 10, params={"data": q})
        r.raise_for_status()
        for e in r.json().get("elements", []):
            tags = e.get("tags", {})
            elat = e.get("lat") or (e.get("center", {}) or {}).get("lat")
            elon = e.get("lon") or (e.get("center", {}) or {}).get("lon")
            if elat is None or elon is None:
                continue
            dist = round(_haversine(lat, lon, elat, elon), 1)
            name = tags.get("name") or "(unnamed)"
            if tags.get("amenity") == "hospital":
                out["hospitals"].append({"name": name, "distance_km": dist,
                                         "beds": tags.get("beds"), "lat": elat, "lon": elon})
            elif tags.get("aeroway") == "aerodrome":
                out["airports"].append({"name": name, "distance_km": dist,
                                        "iata": tags.get("iata"), "icao": tags.get("icao"),
                                        "lat": elat, "lon": elon})
        out["hospitals"].sort(key=lambda x: x["distance_km"])
        out["airports"].sort(key=lambda x: x["distance_km"])
        out["hospitals"] = out["hospitals"][:8]
        out["airports"] = out["airports"][:5]
    except Exception:
        pass
    return _store(ck, out)


def get_satellite(lat: float, lon: float, hazard_type: str = "") -> Optional[Dict[str, Any]]:
    """Near-real-time true-colour satellite image of the area from NASA GIBS /
    Worldview Snapshots (keyless). Returns a directly-embeddable image URL.
    Uses VIIRS (higher-res, 375 m) and falls back a day if today is unprocessed."""
    # MODIS/VIIRS imagery for "today" may not be processed yet — use yesterday UTC
    date = (_dt.datetime.utcnow() - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    half = 0.9  # ~100 km half-box
    s, w, n, e = lat - half, lon - half, lat + half, lon + half
    layer = "VIIRS_SNPP_CorrectedReflectance_TrueColor"
    url = ("https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot"
           f"&LAYERS={layer}&CRS=EPSG:4326&TIME={date}"
           f"&BBOX={s},{w},{n},{e}&WIDTH=640&HEIGHT=640&FORMAT=image/jpeg")
    return {"url": url, "date": date, "layer": "VIIRS true-colour",
            "source": "NASA GIBS / Worldview",
            "worldview": (f"https://worldview.earthdata.nasa.gov/?v={w},{s},{e},{n}"
                          f"&t={date}")}


def get_air_traffic(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Live aircraft within ~150 km from OpenSky (keyless, rate-limited). Useful
    as a real signal of airspace activity / airport operability."""
    ck = f"air:{round(lat,1)}:{round(lon,1)}"
    if (c := _cached(ck)) is not None:
        return c
    d = 1.4
    try:
        r = requests.get("https://opensky-network.org/api/states/all", headers=_HEADERS, timeout=_TIMEOUT,
                         params={"lamin": lat - d, "lomin": lon - d, "lamax": lat + d, "lomax": lon + d})
        r.raise_for_status()
        states = r.json().get("states") or []
        airborne = [s for s in states if not s[8]]
        on_ground = [s for s in states if s[8]]
        sample = [{"callsign": (s[1] or "").strip() or "—", "country": s[2],
                   "alt_m": s[7], "on_ground": s[8]} for s in states[:6]]
        out = {"count": len(states), "airborne": len(airborne), "on_ground": len(on_ground),
               "sample": sample, "source": "OpenSky Network"}
        return _store(ck, out)
    except Exception:
        return None


def get_fires(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Active fire/thermal detections within ~150 km from NASA FIRMS (VIIRS,
    near-real-time). Requires FIRMS_MAP_KEY."""
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        return None
    ck = f"fire:{round(lat,1)}:{round(lon,1)}"
    if (c := _cached(ck)) is not None:
        return c
    d = 1.5  # bbox half-width (deg)
    bbox = f"{lon-d},{lat-d},{lon+d},{lat+d}"  # west,south,east,north
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{bbox}/1"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(r.text)))
        dets = []
        for row in rows:
            try:
                flat, flon = float(row["latitude"]), float(row["longitude"])
            except (KeyError, ValueError):
                continue
            dets.append({"lat": flat, "lon": flon,
                         "frp": float(row.get("frp") or 0),
                         "dist": round(_haversine(lat, lon, flat, flon), 1),
                         "time": f"{row.get('acq_date','')} {row.get('acq_time','')}",
                         "confidence": row.get("confidence")})
        dets.sort(key=lambda x: x["dist"])
        out = {"count": len(dets), "max_frp": round(max([d["frp"] for d in dets], default=0), 1),
               "nearest_km": dets[0]["dist"] if dets else None,
               "detections": dets[:50], "source": "NASA FIRMS (VIIRS)"}
        return _store(ck, out)
    except Exception:
        return None


_AQI_BANDS = [(12, "Good"), (35.4, "Moderate"), (55.4, "Unhealthy (sensitive)"),
              (150.4, "Unhealthy"), (250.4, "Very unhealthy"), (1e9, "Hazardous")]


def get_air_quality(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Latest ground air-quality (PM2.5) near the site from OpenAQ v3.
    Requires OPENAQ_API_KEY."""
    key = os.environ.get("OPENAQ_API_KEY")
    if not key:
        return None
    ck = f"aq:{round(lat,2)}:{round(lon,2)}"
    if (c := _cached(ck)) is not None:
        return c
    h = {**_HEADERS, "X-API-Key": key}
    try:
        loc = requests.get("https://api.openaq.org/v3/locations", headers=h, timeout=_TIMEOUT,
                           params={"coordinates": f"{lat},{lon}", "radius": 25000,
                                   "parameters_id": 2, "limit": 1}).json()
        results = loc.get("results", [])
        if not results:
            return _store(ck, None)
        site = results[0]
        latest = requests.get(f"https://api.openaq.org/v3/locations/{site['id']}/latest",
                              headers=h, timeout=_TIMEOUT).json().get("results", [])
        pm = next((m for m in latest if (m.get("value") is not None)), None)
        if not pm:
            return _store(ck, None)
        val = pm["value"]
        band = next(b[1] for b in _AQI_BANDS if val <= b[0])
        out = {"pm25": val, "band": band, "location": site.get("name"),
               "time": (pm.get("datetime", {}) or {}).get("utc"), "source": "OpenAQ"}
        return _store(ck, out)
    except Exception:
        return None


def get_radar(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Live precipitation-radar tile covering the site from RainViewer (keyless)."""
    ck = f"radar:{round(lat,1)}:{round(lon,1)}"
    if (c := _cached(ck)) is not None:
        return c
    try:
        idx = requests.get("https://api.rainviewer.com/public/weather-maps.json",
                           headers=_HEADERS, timeout=_TIMEOUT).json()
        host = idx.get("host", "https://tilecache.rainviewer.com")
        past = idx.get("radar", {}).get("past", [])
        if not past:
            return _store(ck, None)
        frame = past[-1]
        z = 6
        n = 2 ** z
        x = int((lon + 180.0) / 360.0 * n)
        ymerc = math.asinh(math.tan(math.radians(lat)))
        y = int((1 - ymerc / math.pi) / 2 * n)
        out = {
            "radar_url": f"{host}{frame['path']}/256/{z}/{x}/{y}/4/1_1.png",
            "base_url": f"https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "z": z, "x": x, "y": y,
            "time": _dt.datetime.utcfromtimestamp(frame.get("time", 0)).isoformat() + "Z",
            "source": "RainViewer",
        }
        return _store(ck, out)
    except Exception:
        return None


def _vessel_headers() -> Optional[Dict[str, str]]:
    key = os.environ.get("VESSEL_API_KEY")
    return {**_HEADERS, "Authorization": f"Bearer {key}"} if key else None


def get_vessels(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Live AIS vessel positions within ~80 km (VesselAPI). Maritime SAR-asset /
    shipping awareness for coastal incidents. Returns None inland or without key."""
    h = _vessel_headers()
    if not h:
        return None
    ck = f"vessel:{round(lat,1)}:{round(lon,1)}"
    if (c := _cached(ck)) is not None:
        return c
    try:
        r = requests.get("https://api.vesselapi.com/v1/location/vessels/radius", headers=h,
                         timeout=_TIMEOUT, params={"filter.latitude": lat, "filter.longitude": lon,
                                                    "filter.radius": 80000, "pagination.limit": 50})
        r.raise_for_status()
        vs = r.json().get("vessels", [])
        sample = []
        for v in vs:
            try:
                d = _haversine(lat, lon, v["latitude"], v["longitude"])
            except (KeyError, TypeError):
                continue
            sample.append({"name": v.get("vessel_name") or f"MMSI {v.get('mmsi')}",
                           "mmsi": v.get("mmsi"), "sog": v.get("sog"),
                           "dist_km": round(d, 1), "lat": v["latitude"], "lon": v["longitude"]})
        sample.sort(key=lambda x: x["dist_km"])
        if not sample:
            return _store(ck, None)
        moving = [v for v in sample if (v.get("sog") or 0) > 0.5]
        out = {"count": len(sample), "moving": len(moving),
               "nearest": sample[0], "sample": sample[:10], "source": "VesselAPI (AIS)"}
        return _store(ck, out)
    except Exception:
        return None


def get_ports(lat: float, lon: float) -> List[Dict[str, Any]]:
    """Nearest seaports within 100 km (VesselAPI) — sea relief-logistics access."""
    h = _vessel_headers()
    if not h:
        return []
    ck = f"ports:{round(lat,1)}:{round(lon,1)}"
    if (c := _cached(ck)) is not None:
        return c
    out = []
    try:
        r = requests.get("https://api.vesselapi.com/v1/location/ports/radius", headers=h,
                         timeout=_TIMEOUT, params={"filter.latitude": lat, "filter.longitude": lon,
                                                    "filter.radius": 100000, "pagination.limit": 30})
        r.raise_for_status()
        seen = set()
        for p in r.json().get("ports", []):
            try:
                d = _haversine(lat, lon, p["latitude"], p["longitude"])
            except (KeyError, TypeError):
                continue
            key = p.get("unlo_code") or (p.get("name"), round(p["latitude"], 2), round(p["longitude"], 2))
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": p.get("name"), "unlocode": p.get("unlo_code"),
                        "country": (p.get("country") or {}).get("name"),
                        "distance_km": round(d, 1)})
        out.sort(key=lambda x: x["distance_km"])
        out = out[:5]
    except Exception:
        pass
    return _store(ck, out)


def get_vessel_tracks(lat: float, lon: float, n: int = 8) -> Dict[str, Any]:
    """Recent tracks (routes) for the nearest vessels, for the 3D globe.
    Current positions from the radius endpoint; tracks from the multi-vessel
    positions endpoint over the last ~3 h."""
    h = _vessel_headers()
    vs = get_vessels(lat, lon)
    if not (h and vs and vs.get("sample")):
        return {"tracks": [], "count": 0}
    nearest = vs["sample"][:n]
    ids = ",".join(str(v["mmsi"]) for v in nearest if v.get("mmsi"))
    frm = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_mmsi: Dict[Any, Dict[str, Any]] = {}
    try:
        r = requests.get("https://api.vesselapi.com/v1/vessels/positions", headers=h, timeout=_TIMEOUT,
                         params={"filter.ids": ids, "filter.idType": "mmsi",
                                 "time.from": frm, "pagination.limit": 50})
        r.raise_for_status()
        for p in r.json().get("vesselPositions", []):
            m = p.get("mmsi")
            if m is None or p.get("latitude") is None:
                continue
            by_mmsi.setdefault(m, {"mmsi": m, "name": p.get("vessel_name") or f"MMSI {m}", "pts": []})
            by_mmsi[m]["pts"].append((p.get("timestamp") or "", p["latitude"], p["longitude"]))
    except Exception:
        pass
    tracks = []
    for v in nearest:
        m = v.get("mmsi")
        rec = by_mmsi.get(m)
        if rec and len(rec["pts"]) >= 2:
            rec["pts"].sort(key=lambda x: x[0])
            path = [[p[1], p[2]] for p in rec["pts"]]
        else:
            path = [[v["lat"], v["lon"]]]  # single point if no history
        tracks.append({"mmsi": m, "name": v.get("name"), "sog": v.get("sog"),
                       "dist_km": v.get("dist_km"), "path": path,
                       "current": [v["lat"], v["lon"]]})
    return {"tracks": tracks, "count": vs.get("count", len(tracks))}


_acled_token: Dict[str, Any] = {}


def _acled_get_token() -> Optional[str]:
    email = os.environ.get("ACLED_EMAIL")
    pw = os.environ.get("ACLED_PASSWORD")
    if not (email and pw):
        return None
    if _acled_token.get("token") and time.time() < _acled_token.get("exp", 0):
        return _acled_token["token"]
    try:
        r = requests.post("https://acleddata.com/oauth/token", headers=_HEADERS, timeout=_TIMEOUT,
                          data={"username": email, "password": pw, "grant_type": "password",
                                "client_id": "acled", "scope": "authenticated"})
        j = r.json()
        tok = j.get("access_token")
        if tok:
            _acled_token["token"] = tok
            _acled_token["exp"] = time.time() + (j.get("expires_in", 3600) - 60)
            return tok
    except Exception:
        pass
    return None


def get_conflict(lat: float, lon: float, country: str = "") -> Optional[Dict[str, Any]]:
    """Recent armed-conflict / unrest events near the site from ACLED.
    Requires ACLED_EMAIL/ACLED_PASSWORD AND API access enabled on the account
    (reads return 'Access denied' until activated)."""
    tok = _acled_get_token()
    if not tok:
        return None
    ck = f"acled:{round(lat,1)}:{round(lon,1)}"
    if (c := _cached(ck)) is not None:
        return c
    try:
        r = requests.get("https://acleddata.com/api/acled/read",
                         headers={**_HEADERS, "Authorization": f"Bearer {tok}"},
                         timeout=_TIMEOUT, params={"limit": 20, "_format": "json"})
        j = r.json()
        if isinstance(j, dict) and j.get("message"):     # e.g. "Access denied"
            return _store(ck, {"available": False, "events": [], "note": j["message"]})
        data = (j.get("data") if isinstance(j, dict) else j) or []
        events = []
        for e in data:
            try:
                elat, elon = float(e.get("latitude")), float(e.get("longitude"))
            except (TypeError, ValueError):
                continue
            dist = _haversine(lat, lon, elat, elon)
            if dist <= 300:
                events.append({"date": e.get("event_date"), "type": e.get("event_type"),
                               "where": e.get("location"), "fatalities": e.get("fatalities"),
                               "dist_km": round(dist, 1)})
        events.sort(key=lambda x: x["dist_km"])
        return _store(ck, {"available": True, "events": events[:8], "source": "ACLED"})
    except Exception:
        return None


def get_context(lat: Optional[float], lon: Optional[float], hazard_type: str = "") -> Dict[str, Any]:
    """Combined operating context for an incident location."""
    if lat is None or lon is None:
        return {"available": False, "weather": None, "hospitals": [], "airports": [],
                "satellite": None, "air_traffic": None, "sources": []}
    # fetch all independent sources concurrently (different hosts) for speed
    satellite = get_satellite(lat, lon, hazard_type)   # URL-only, no network
    with ThreadPoolExecutor(max_workers=9) as ex:
        f_weather = ex.submit(get_weather, lat, lon)
        f_fac = ex.submit(get_facilities, lat, lon)
        f_air = ex.submit(get_air_traffic, lat, lon)
        f_radar = ex.submit(get_radar, lat, lon)
        f_fires = ex.submit(get_fires, lat, lon)
        f_aq = ex.submit(get_air_quality, lat, lon)
        f_conflict = ex.submit(get_conflict, lat, lon)
        f_vessels = ex.submit(get_vessels, lat, lon)
        f_ports = ex.submit(get_ports, lat, lon)
    weather, fac, air = f_weather.result(), f_fac.result(), f_air.result()
    radar, fires, air_quality = f_radar.result(), f_fires.result(), f_aq.result()
    conflict, vessels, ports = f_conflict.result(), f_vessels.result(), f_ports.result()
    sources = []
    if weather:
        sources.append({"name": "Open-Meteo", "url": "https://open-meteo.com"})
    if fac["hospitals"] or fac["airports"]:
        sources.append({"name": "OpenStreetMap / Overpass", "url": "https://www.openstreetmap.org"})
    if satellite:
        sources.append({"name": "NASA GIBS (satellite)", "url": "https://worldview.earthdata.nasa.gov"})
    if air:
        sources.append({"name": "OpenSky (live flights)", "url": "https://opensky-network.org"})
    if radar:
        sources.append({"name": "RainViewer (radar)", "url": "https://www.rainviewer.com"})
    if fires and fires.get("count"):
        sources.append({"name": "NASA FIRMS (active fires)", "url": "https://firms.modaps.eosdis.nasa.gov"})
    if air_quality:
        sources.append({"name": "OpenAQ (air quality)", "url": "https://openaq.org"})
    if conflict and conflict.get("available") and conflict.get("events"):
        sources.append({"name": "ACLED (conflict)", "url": "https://acleddata.com"})
    if vessels or ports:
        sources.append({"name": "VesselAPI (AIS / ports)", "url": "https://vesselapi.com"})
    return {
        "available": bool(weather or fac["hospitals"] or fac["airports"] or satellite),
        "weather": weather, "hospitals": fac["hospitals"], "airports": fac["airports"],
        "satellite": satellite, "air_traffic": air, "radar": radar,
        "fires": fires, "air_quality": air_quality, "conflict": conflict,
        "vessels": vessels, "ports": ports,
        "sources": sources,
    }
