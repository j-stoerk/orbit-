"""Geocoding skill — OSM Nominatim (keyless), with a small offline fallback
gazetteer so the platform still resolves major locations without network."""
from __future__ import annotations
import time
from typing import Optional, Tuple, Dict

import requests

_HEADERS = {"User-Agent": "UNDAC-CrisisCoordinator/2.0"}
_CACHE: Dict[str, Optional[Tuple[float, float]]] = {}
_last_call = 0.0

# Minimal offline gazetteer for common demo / disaster-prone locations
_FALLBACK: Dict[str, Tuple[float, float]] = {
    "los angeles": (34.0522, -118.2437),
    "san francisco": (37.7749, -122.4194),
    "miami": (25.7617, -80.1918),
    "tokyo": (35.6762, 139.6503),
    "manila": (14.5995, 120.9842),
    "jakarta": (-6.2088, 106.8456),
    "istanbul": (41.0082, 28.9784),
    "kathmandu": (27.7172, 85.3240),
    "port-au-prince": (18.5944, -72.3074),
    "haiti": (18.9712, -72.2852),
    "nepal": (28.3949, 84.1240),
    "turkey": (38.9637, 35.2433),
    "syria": (34.8021, 38.9968),
    "morocco": (31.7917, -7.0926),
    "libya": (26.3351, 17.2283),
    "philippines": (12.8797, 121.7740),
    "indonesia": (-0.7893, 113.9213),
    "japan": (36.2048, 138.2529),
    "mozambique": (-18.6657, 35.5296),
    "bangladesh": (23.6850, 90.3563),
    "pakistan": (30.3753, 69.3451),
    "somalia": (5.1521, 46.1996),
    "ukraine": (48.3794, 31.1656),
}


def get_coordinates(location_name: str) -> Optional[Tuple[float, float]]:
    if not location_name:
        return None
    key = location_name.strip().lower()
    if key in _CACHE:
        return _CACHE[key]

    global _last_call
    # Nominatim asks for <=1 req/sec
    delta = time.time() - _last_call
    if delta < 1.1:
        time.sleep(1.1 - delta)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            headers=_HEADERS,
            params={"q": location_name, "format": "json", "limit": 1},
            timeout=10,
        )
        _last_call = time.time()
        resp.raise_for_status()
        data = resp.json()
        if data:
            result = (float(data[0]["lat"]), float(data[0]["lon"]))
            _CACHE[key] = result
            return result
    except Exception:
        pass

    # offline fallback
    for name, coords in _FALLBACK.items():
        if name in key or key in name:
            _CACHE[key] = coords
            return coords
    _CACHE[key] = None
    return None
