import requests
from typing import Tuple, Optional

def get_coordinates(location_name: str) -> Optional[Tuple[float, float]]:
    """
    Skill: Geocoding
    Converts a location string into (latitude, longitude) using OSM Nominatim API.
    """
    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        'User-Agent': 'CrisisCoordinationAgent/1.0'
    }
    params = {
        'q': location_name,
        'format': 'json',
        'limit': 1
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            return (lat, lon)
        return None
    except Exception as e:
        print(f"[Geocoder] Error geocoding {location_name}: {e}")
        return None
