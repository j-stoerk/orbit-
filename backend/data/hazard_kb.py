"""
Hazard Impact Knowledge Base.

Grounded in the UNDAC Handbook (8th Edition, 2024), Section K — "Hazard Impact
Summaries" (K.1 Earthquakes, K.2 Tsunamis, K.3 Tropical Cyclones, K.4 Floods,
K.5 Volcanoes, K.6 Wildfires, K.7 Droughts).

Each entry encodes the characteristic secondary hazards, the humanitarian
sectors typically most affected (per the IASC cluster system), priority early
actions, and the assessment indicators an UNDAC team would prioritise. The
Assessment Agent uses this to produce hazard-aware MIRA-style needs estimates
without requiring an LLM.
"""

from typing import Dict, List, Any

# IASC / UNDAC humanitarian sectors (clusters)
SECTORS = [
    "Health",
    "WASH",            # Water, Sanitation and Hygiene
    "Shelter/NFI",
    "Food Security",
    "Protection",
    "Logistics",
    "Emergency Telecommunications",
    "Education",
    "Early Recovery",
]

HAZARD_PROFILES: Dict[str, Dict[str, Any]] = {
    "Earthquake": {
        "handbook_ref": "K.1",
        "secondary_hazards": [
            "Aftershocks", "Building collapse", "Landslides",
            "Fires", "Tsunami (if offshore)", "Dam/levee failure",
        ],
        "priority_sectors": ["Health", "Shelter/NFI", "WASH", "Logistics", "Protection"],
        "priority_actions": [
            "Deploy Urban Search & Rescue (USAR/INSARAG) to collapsed structures",
            "Establish field medical / EMT triage for trauma & crush injuries",
            "Rapid structural safety assessment of hospitals & shelters",
            "Restore water supply; prevent waterborne disease",
            "Set up emergency shelter for displaced households",
        ],
        "assessment_indicators": [
            "Number & location of collapsed structures",
            "Estimated people trapped / casualties",
            "Hospital functionality & surge capacity",
            "Road & bridge access status",
            "Displaced population & shelter needs",
        ],
        "key_resources": ["medics", "rescue_teams", "tents", "water", "ambulances", "helicopters"],
        "golden_hours": 72,  # USAR live-rescue window
    },
    "Tsunami": {
        "handbook_ref": "K.2",
        "secondary_hazards": [
            "Repeated wave surges", "Coastal flooding", "Saltwater contamination",
            "Debris fields", "Infrastructure destruction",
        ],
        "priority_sectors": ["WASH", "Health", "Shelter/NFI", "Food Security", "Protection"],
        "priority_actions": [
            "Confirm evacuation of low-lying coastal zones",
            "Search & rescue along inundation line",
            "Provide safe drinking water (wells saltwater-contaminated)",
            "Mass-casualty management & drowning/trauma care",
            "Emergency shelter on high ground",
        ],
        "assessment_indicators": [
            "Inundation extent & affected coastline (km)",
            "Coastal population displaced",
            "Water source contamination",
            "Port & airport operability for relief",
            "Missing persons count",
        ],
        "key_resources": ["rescue_boats", "water", "medics", "tents", "food_rations", "body_bags"],
        "golden_hours": 48,
    },
    "Tropical Cyclone": {
        "handbook_ref": "K.3",
        "secondary_hazards": [
            "Storm surge", "Flooding", "Landslides", "Wind damage",
            "Power & communications loss",
        ],
        "priority_sectors": ["Shelter/NFI", "WASH", "Health", "Food Security", "Logistics"],
        "priority_actions": [
            "Pre-positioning & evacuation ahead of landfall",
            "Restore emergency telecommunications",
            "Distribute shelter / tarpaulins for damaged housing",
            "Clear access routes for relief convoys",
            "Prevent vector- & water-borne disease outbreaks",
        ],
        "assessment_indicators": [
            "Wind speed category & track",
            "Storm-surge inundation",
            "Damaged/destroyed houses",
            "Power & telecom outages",
            "Crop & livelihood losses",
        ],
        "key_resources": ["tents", "tarpaulins", "water", "food_rations", "generators", "helicopters"],
        "golden_hours": 96,
    },
    "Flood": {
        "handbook_ref": "K.4",
        "secondary_hazards": [
            "Waterborne disease", "Crop destruction", "Displacement",
            "Contaminated water", "Stranded populations",
        ],
        "priority_sectors": ["WASH", "Health", "Shelter/NFI", "Food Security", "Protection"],
        "priority_actions": [
            "Boat-based rescue of stranded populations",
            "Provide safe water & sanitation to prevent cholera/diarrhoea",
            "Evacuation & temporary shelter for displaced",
            "Distribute food where crops/markets destroyed",
            "Disease surveillance & oral rehydration",
        ],
        "assessment_indicators": [
            "Flood extent & depth",
            "Population displaced / stranded",
            "Water source contamination",
            "Submerged farmland (food security)",
            "Health facility access",
        ],
        "key_resources": ["rescue_boats", "water", "food_rations", "tents", "medics", "water_purification"],
        "golden_hours": 72,
    },
    "Volcano": {
        "handbook_ref": "K.5",
        "secondary_hazards": [
            "Pyroclastic flows", "Ashfall", "Lahars (mudflows)",
            "Toxic gases", "Respiratory hazards",
        ],
        "priority_sectors": ["Health", "Shelter/NFI", "WASH", "Protection", "Logistics"],
        "priority_actions": [
            "Enforce exclusion zone & evacuate at-risk communities",
            "Distribute respiratory protection (ashfall)",
            "Provide clean water (ash-contaminated supplies)",
            "Treat burns & respiratory casualties",
            "Shelter evacuees beyond hazard radius",
        ],
        "assessment_indicators": [
            "Eruption type & exclusion radius",
            "Population within hazard zone",
            "Ashfall depth & air quality",
            "Evacuation completeness",
            "Water & crop contamination",
        ],
        "key_resources": ["masks", "water", "tents", "medics", "buses", "food_rations"],
        "golden_hours": 48,
    },
    "Wildfire": {
        "handbook_ref": "K.6",
        "secondary_hazards": [
            "Smoke & air quality", "Rapid spread", "Infrastructure loss",
            "Post-fire flooding/erosion", "Power loss",
        ],
        "priority_sectors": ["Health", "Shelter/NFI", "Protection", "Logistics", "WASH"],
        "priority_actions": [
            "Evacuate communities in the fire path",
            "Air-quality / respiratory health response",
            "Emergency shelter for displaced households",
            "Burn & smoke-inhalation medical care",
            "Protect critical infrastructure & access routes",
        ],
        "assessment_indicators": [
            "Fire perimeter & rate of spread",
            "Communities & structures threatened",
            "Air quality index",
            "Population evacuated",
            "Burn casualties",
        ],
        "key_resources": ["masks", "buses", "tents", "medics", "water", "food_rations"],
        "golden_hours": 24,
    },
    "Drought": {
        "handbook_ref": "K.7",
        "secondary_hazards": [
            "Crop failure", "Food insecurity", "Water scarcity",
            "Livestock loss", "Displacement & migration",
        ],
        "priority_sectors": ["Food Security", "WASH", "Health", "Protection", "Early Recovery"],
        "priority_actions": [
            "Emergency water trucking to affected communities",
            "Food assistance / cash transfers against acute malnutrition",
            "Nutrition screening for children under 5",
            "Livestock & livelihood support",
            "Monitor displacement & resource-driven conflict",
        ],
        "assessment_indicators": [
            "Rainfall deficit & duration",
            "Population food-insecure (IPC phase)",
            "Water-point functionality",
            "Acute malnutrition rates",
            "Livestock mortality",
        ],
        "key_resources": ["water", "food_rations", "water_purification", "medics", "cash_transfers"],
        "golden_hours": 0,  # slow-onset
    },
}

# Default profile for unknown / generic hazards
GENERIC_PROFILE: Dict[str, Any] = {
    "handbook_ref": "A",
    "secondary_hazards": ["Cascading infrastructure failure", "Displacement"],
    "priority_sectors": ["Health", "WASH", "Shelter/NFI", "Logistics", "Protection"],
    "priority_actions": [
        "Conduct rapid multi-sector needs assessment (MIRA)",
        "Establish coordination (OSOCC) with national authorities",
        "Identify life-saving priorities and access constraints",
    ],
    "assessment_indicators": [
        "Affected & displaced population",
        "Access & infrastructure status",
        "Critical sectoral needs",
    ],
    "key_resources": ["water", "food_rations", "tents", "medics"],
    "golden_hours": 72,
}


def get_hazard_profile(disaster_type: str) -> Dict[str, Any]:
    """Return the hazard impact profile for a disaster type (case-insensitive,
    tolerant of common synonyms)."""
    if not disaster_type:
        return GENERIC_PROFILE
    key = disaster_type.strip().lower()
    synonyms = {
        "earthquake": "Earthquake", "quake": "Earthquake", "seismic": "Earthquake",
        "tsunami": "Tsunami", "tidal wave": "Tsunami",
        "cyclone": "Tropical Cyclone", "hurricane": "Tropical Cyclone",
        "typhoon": "Tropical Cyclone", "tropical cyclone": "Tropical Cyclone",
        "storm": "Tropical Cyclone",
        "flood": "Flood", "flooding": "Flood", "inundation": "Flood",
        "volcano": "Volcano", "volcanic": "Volcano", "eruption": "Volcano",
        "wildfire": "Wildfire", "fire": "Wildfire", "bushfire": "Wildfire",
        "drought": "Drought", "famine": "Drought",
    }
    for token, canonical in synonyms.items():
        if token in key:
            return HAZARD_PROFILES[canonical]
    return GENERIC_PROFILE


def list_hazards() -> List[str]:
    return list(HAZARD_PROFILES.keys())
