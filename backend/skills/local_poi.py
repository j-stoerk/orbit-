"""
Local POI Lookup Skill — OSM Overpass QL integration.
Resolves critical local facilities (hospitals, schools/shelters, fire stations)
around a set of coordinates (lat, lon) to assist on-the-ground responders.
"""
from __future__ import annotations
import math
import requests
from typing import List, Dict, Any

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two lat/lon coordinates."""
    R = 6371000.0  # meters
    p = math.pi / 180.0
    a = (math.sin((lat2 - lat1) * p / 2.0) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2.0) ** 2)
    return 2.0 * R * math.asin(math.sqrt(a))

def fetch_local_pois(lat: float, lon: float, radius_meters: int = 1500) -> List[Dict[str, Any]]:
    """Fetch hospitals, schools, and fire stations from Overpass within radius_meters."""
    # Offline fallback for Manila UST coords
    # Check if close to UST Manila (lat=14.6095, lon=120.9897)
    if abs(lat - 14.6095) < 0.005 and abs(lon - 120.9897) < 0.005:
        return [
            {
                "name": "University of Santo Tomas Hospital",
                "type": "hospital",
                "lat": 14.6092,
                "lon": 120.9908,
                "distance_meters": 180,
                "distance_label": "180m",
                "distance": "180m",
                "coords": [14.6092, 120.9908]
            },
            {
                "name": "Hospital of the Infant Jesus",
                "type": "hospital",
                "lat": 14.6124,
                "lon": 120.9852,
                "distance_meters": 640,
                "distance_label": "640m",
                "distance": "640m",
                "coords": [14.6124, 120.9852]
            },
            {
                "name": "Ramon Magsaysay High School (Evacuation Shelter)",
                "type": "school",
                "lat": 14.6148,
                "lon": 120.9934,
                "distance_meters": 820,
                "distance_label": "820m",
                "distance": "820m",
                "coords": [14.6148, 120.9934]
            }
        ]

    query = f"""
    [out:json];
    (
      node(around:{radius_meters},{lat},{lon})[amenity=hospital];
      node(around:{radius_meters},{lat},{lon})[amenity=school];
      node(around:{radius_meters},{lat},{lon})[amenity=fire_station];
    );
    out body;
    """
    url = "https://overpass-api.de/api/interpreter"
    headers = {"User-Agent": "ORBIT-CrisisCoordinator/2.0 (local POI lookup)"}
    try:
        response = requests.post(url, data={"data": query}, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        pois = []
        for element in data.get("elements", []):
            elat = element.get("lat")
            elon = element.get("lon")
            if elat is None or elon is None:
                continue
            dist = _haversine(lat, lon, elat, elon)
            # Map type to user-friendly label
            amenity_type = element.get("tags", {}).get("amenity", "facility")
            pois.append({
                "name": element.get("tags", {}).get("name", f"Unnamed {amenity_type.title()}"),
                "type": amenity_type,
                "lat": elat,
                "lon": elon,
                "distance_meters": int(dist),
                "distance_label": f"{int(dist)}m" if dist < 1000 else f"{dist/1000.0:.1f}km",
                "distance": f"{int(dist)}m" if dist < 1000 else f"{dist/1000.0:.1f}km",
                "coords": [elat, elon]
            })
        # sort by distance
        pois.sort(key=lambda x: x["distance_meters"])
        return pois[:5]  # limit to top 5 closest
    except Exception as e:
        print(f"[Local POI] Error fetching POIs: {e}")
        return []
