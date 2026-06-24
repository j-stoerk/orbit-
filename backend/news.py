"""
Live news & social media — real, keyless sources for situational awareness.

  * News   — GDELT DOC 2.0 (global news monitoring). Rate-limited upstream
             (≈1 request / 5 s), so results are cached and throttled.
  * Social — Mastodon public hashtag timelines (keyless, real public posts).

Both are returned with source attribution; nothing is synthesised.
"""
from __future__ import annotations
import re
import time
import html
import threading
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from urllib.parse import quote

import requests

_HEADERS = {"User-Agent": "ORBIT-CrisisCoordinator/1.0 (situational awareness)"}
_TIMEOUT = 12
_CACHE: Dict[str, Any] = {}
_TTL = 600
_gdelt_lock = threading.Lock()
_gdelt_last = 0.0

_TAG = {
    "earthquake": "earthquake", "tsunami": "tsunami", "tropical cyclone": "cyclone",
    "flood": "flood", "volcano": "volcano", "wildfire": "wildfire", "drought": "drought",
}


def _cached(k):
    e = _CACHE.get(k)
    return e["v"] if e and time.time() - e["t"] < _TTL else None


def _store(k, v):
    _CACHE[k] = {"t": time.time(), "v": v}
    return v


def _strip(htmltext: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", htmltext or "")).strip()


def _google_news(query: str, limit: int) -> List[Dict[str, Any]]:
    """Primary news source: Google News RSS (keyless, reliable).
    Restricts to the last 14 days (`when:14d`) and sorts newest-first so results
    are genuinely current, not relevance-ranked old articles."""
    from email.utils import parsedate_to_datetime
    q = f"{query} when:14d"
    url = (f"https://news.google.com/rss/search?q={quote(q)}"
           "&hl=en-US&gl=US&ceid=US:en")
    items: List[Dict[str, Any]] = []
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (ORBIT)"}, timeout=_TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    for it in root.findall(".//item"):
        title = it.findtext("title") or ""
        src = it.find("{*}source")
        pub = it.findtext("pubDate") or ""
        try:
            ts = parsedate_to_datetime(pub).timestamp()
        except Exception:
            ts = 0
        items.append({
            "title": title, "url": it.findtext("link"),
            "domain": (src.text if src is not None else ""),
            "time": pub[:16], "_ts": ts,
            "image": None, "country": "", "source": "Google News", "kind": "news",
        })
    items.sort(key=lambda x: x["_ts"], reverse=True)   # newest first
    for x in items:
        x.pop("_ts", None)
    return items[:limit]


def _gdelt_news(query: str, limit: int) -> List[Dict[str, Any]]:
    """Fallback news source: GDELT DOC 2.0 (rate-limited ≈1 req/5 s)."""
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?"
           f"query={quote(query)}&mode=ArtList&maxrecords={limit}"
           "&format=json&timespan=7d&sort=DateDesc")
    out: List[Dict[str, Any]] = []
    global _gdelt_last
    with _gdelt_lock:
        wait = 5.5 - (time.time() - _gdelt_last)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        _gdelt_last = time.time()
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
        for a in r.json().get("articles", []):
            out.append({
                "title": a.get("title"), "url": a.get("url"),
                "domain": a.get("domain"), "time": a.get("seendate"),
                "image": a.get("socialimage"), "country": a.get("sourcecountry"),
                "source": "GDELT", "kind": "news",
            })
    return out


def get_news(query: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Recent news about `query`. Google News RSS primary, GDELT fallback."""
    query = (query or "").strip()
    if not query:
        return []
    ck = f"news:{query}:{limit}"
    if (c := _cached(ck)) is not None:
        return c
    out: List[Dict[str, Any]] = []
    try:
        out = _google_news(query, limit)
    except Exception:
        out = []
    if not out:
        try:
            out = _gdelt_news(query, limit)
        except Exception:
            out = []
    return _store(ck, out)


def get_social(hazard_type: str, location: str = "", limit: int = 12) -> List[Dict[str, Any]]:
    """Recent public Mastodon posts for the hazard hashtag, lightly filtered by
    location mention when a location is given."""
    tag = _TAG.get((hazard_type or "").strip().lower(), "")
    if not tag:
        tag = re.sub(r"[^a-z]", "", (hazard_type or "alert").lower()) or "alert"
    ck = f"social:{tag}:{location}:{limit}"
    if (c := _cached(ck)) is not None:
        return c
    url = f"https://mastodon.social/api/v1/timelines/tag/{tag}?limit=40"
    out: List[Dict[str, Any]] = []
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        loc = (location or "").split(",")[0].strip().lower()
        for p in r.json():
            text = _strip(p.get("content", ""))
            if loc and loc not in text.lower():
                continue
            acct = p.get("account", {})
            out.append({
                "text": text[:280], "author": acct.get("acct"),
                "display_name": acct.get("display_name"), "avatar": acct.get("avatar"),
                "url": p.get("url"), "time": p.get("created_at"),
                "source": "Mastodon", "kind": "social",
            })
            if len(out) >= limit:
                break
        # if location filter was too strict, fall back to unfiltered top posts
        if loc and not out:
            for p in r.json()[:limit]:
                acct = p.get("account", {})
                out.append({
                    "text": _strip(p.get("content", ""))[:280], "author": acct.get("acct"),
                    "display_name": acct.get("display_name"), "avatar": acct.get("avatar"),
                    "url": p.get("url"), "time": p.get("created_at"),
                    "source": "Mastodon", "kind": "social",
                })
    except Exception:
        pass
    return _store(ck, out)


def get_media(location: str, hazard_type: str) -> Dict[str, Any]:
    """Combined news + social for an incident location/hazard."""
    q = " ".join(x for x in [(location or "").split(",")[0].strip(), hazard_type] if x).strip()
    return {
        "query": q,
        "news": get_news(q or hazard_type, 12),
        "social": get_social(hazard_type, location, 12),
    }
