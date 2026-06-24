"""
Real exposure & impact estimates — strictly sourced, never fabricated.

  * USGS PAGER  — population exposed to damaging shaking (MMI ≥ 6) and the
    official PAGER fatality/economic alert bands.
  * GDACS       — alert level, human-readable severity, and `sendai` reported
    impacts (dead / displaced / affected) when authorities have reported them.

Every figure returned carries a source. When a value is genuinely unknown, it is
returned as ``None`` (the UI shows "not estimated") rather than invented.
"""
from __future__ import annotations
import time
from typing import Dict, Any, List, Optional

import requests

_TIMEOUT = 12
_HEADERS = {"User-Agent": "UNDAC-CrisisCoordinator/2.0"}
_CACHE: Dict[str, Any] = {}
_TTL = 600


def _cached(k):
    e = _CACHE.get(k)
    return e["v"] if e and time.time() - e["t"] < _TTL else None


def _store(k, v):
    _CACHE[k] = {"t": time.time(), "v": v}
    return v


def _blank() -> Dict[str, Any]:
    return {
        "affected": None, "affected_label": "",
        "fatalities": None, "fatalities_label": "",
        "displaced": None, "displaced_label": "",
        "alert_level": None, "severity_text": "",
        "reported": False, "sources": [], "available": False, "shakemap_url": None,
    }


# Official USGS PAGER fatality alert bands (documented thresholds)
_PAGER_FATALITY = {
    "green": "0 estimated fatalities (low likelihood)",
    "yellow": "1–99 estimated fatalities (PAGER yellow)",
    "orange": "100–999 estimated fatalities (PAGER orange)",
    "red": "1,000+ estimated fatalities (PAGER red)",
}


def usgs_pager_exposure(detail_url: str) -> Dict[str, Any]:
    """Fetch PAGER population exposure + fatality band for a USGS event."""
    if not detail_url:
        return _blank()
    ck = f"usgs:{detail_url}"
    if (c := _cached(ck)) is not None:
        return c
    out = _blank()
    try:
        d = requests.get(detail_url, headers=_HEADERS, timeout=_TIMEOUT).json()
        page = d.get("properties", {}).get("url")
        out["sources"].append({"name": "USGS PAGER", "url": page or detail_url})
        prods = d.get("properties", {}).get("products", {})
        # ShakeMap intensity image (real map of ground shaking)
        sm = (prods.get("shakemap") or [None])[0]
        if sm:
            c = sm.get("contents", {})
            img = c.get("download/intensity.jpg") or c.get("intensity.jpg")
            if img:
                out["shakemap_url"] = img.get("url")
        lp = (prods.get("losspager") or [None])[0]
        if not lp:
            return _store(ck, out)
        out["available"] = True
        alert = (lp.get("properties", {}) or {}).get("alertlevel")
        out["alert_level"] = alert
        if alert:
            out["fatalities_label"] = _PAGER_FATALITY.get(alert, "")
        # population exposed to MMI >= 6 (potentially damaging shaking)
        exp_url = None
        for name, c in (lp.get("contents") or {}).items():
            if name.endswith("json/exposures.json"):
                exp_url = c.get("url"); break
        if exp_url:
            ex = requests.get(exp_url, headers=_HEADERS, timeout=_TIMEOUT).json()
            pe = ex.get("population_exposure", {})
            mmi = pe.get("mmi", [])
            agg = pe.get("aggregated_exposure", [])
            if mmi and agg and len(mmi) == len(agg):
                strong = sum(a for m, a in zip(mmi, agg) if m >= 6)
                felt = sum(a for m, a in zip(mmi, agg) if m >= 4)
                out["affected"] = int(strong)
                out["affected_label"] = "people exposed to strong shaking (MMI ≥ 6)"
                if strong == 0 and felt:
                    out["affected"] = 0
                    out["affected_label"] = (
                        f"0 exposed to damaging shaking; ~{int(felt):,} felt it (MMI ≥ 4)")
    except Exception:
        pass
    return _store(ck, out)


def _num(v) -> Optional[int]:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def gdacs_exposure(eventtype: str, eventid: str) -> Dict[str, Any]:
    """Fetch GDACS alert level, severity text and reported `sendai` impacts."""
    if not (eventtype and eventid):
        return _blank()
    ck = f"gdacs:{eventtype}:{eventid}"
    if (c := _cached(ck)) is not None:
        return c
    out = _blank()
    try:
        url = f"https://www.gdacs.org/gdacsapi/api/events/geteventdata?eventtype={eventtype}&eventid={eventid}"
        p = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT).json().get("properties", {})
        out["available"] = True
        out["alert_level"] = p.get("alertlevel")
        out["severity_text"] = (p.get("severitydata", {}) or {}).get("severitytext", "")
        report = p.get("url", {}).get("report") if isinstance(p.get("url"), dict) else None
        out["sources"].append({"name": "GDACS", "url": report or "https://www.gdacs.org"})

        # `sendai` = authority-reported impacts (real ground truth when present)
        buckets: Dict[str, int] = {}
        for s in (p.get("sendai") or []):
            name = (s.get("sendainame") or "").lower()
            val = _num(s.get("sendaivalue"))
            if val is None:
                continue
            buckets[name] = buckets.get(name, 0) + val
        if buckets:
            out["reported"] = True
            dead = buckets.get("dead") or buckets.get("deaths") or buckets.get("death")
            disp = buckets.get("displaced") or buckets.get("evacuated") or buckets.get("relocated")
            aff = buckets.get("affected") or buckets.get("total affected")
            if dead is not None:
                out["fatalities"] = dead
                out["fatalities_label"] = "reported dead (GDACS / national authorities)"
            if disp is not None:
                out["displaced"] = disp
                out["displaced_label"] = "reported displaced/evacuated (GDACS)"
            if aff is not None:
                out["affected"] = aff
                out["affected_label"] = "reported affected (GDACS)"
    except Exception:
        pass
    return _store(ck, out)


def resolve_exposure(ref: Dict[str, Any]) -> Dict[str, Any]:
    """Given a live-event identity reference, return real exposure or a blank
    (all-None) result. `ref` keys: source, detail (USGS), gdacs_eventtype,
    gdacs_eventid."""
    if not ref:
        return _blank()
    src = (ref.get("source") or "").upper()
    if src == "USGS":
        return usgs_pager_exposure(ref.get("detail"))
    if src == "GDACS":
        return gdacs_exposure(ref.get("gdacs_eventtype"), ref.get("gdacs_eventid"))
    return _blank()
