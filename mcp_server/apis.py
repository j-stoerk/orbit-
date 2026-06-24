import requests
from typing import Dict, Any

def get_usgs_earthquakes(min_magnitude: float = 4.0) -> Dict[str, Any]:
    """
    Fetches recent earthquakes from USGS API.
    """
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        # Filter by magnitude
        filtered_features = [
            f for f in data.get("features", [])
            if f.get("properties", {}).get("mag", 0) >= min_magnitude
        ]
        return {
            "type": "FeatureCollection",
            "metadata": data.get("metadata"),
            "features": filtered_features[:5] # limit to 5 for brevity
        }
    except Exception as e:
        return {"error": str(e)}

def get_gdacs_alerts() -> Dict[str, Any]:
    """
    Fetches current global disaster alerts from GDACS.
    """
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP?alertlevel=Orange,Red"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        # Filter to active only
        features = data.get("features", [])
        return {
            "events": [
                {
                    "name": f.get("properties", {}).get("name"),
                    "eventtype": f.get("properties", {}).get("eventtype"),
                    "alertlevel": f.get("properties", {}).get("alertlevel"),
                    "country": f.get("properties", {}).get("country")
                }
                for f in features[:5]
            ]
        }
    except Exception as e:
        return {"error": str(e)}
