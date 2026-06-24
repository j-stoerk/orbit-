from pydantic import BaseModel
from typing import List

class DisasterIncident(BaseModel):
    disaster_type: str
    location: str
    estimated_casualties: int
    specific_needs: List[str]
    raw_report: str

def run_ingestion_agent(raw_report: str) -> DisasterIncident:
    """
    Ingestion Agent: Parses unstructured raw text into structured DisasterIncident.
    (Mock implementation simulating an LLM structured output call)
    """
    print(f"[Ingestion Agent] Parsing raw report: {raw_report}")
    
    # In a real ADK, we would call an LLM here with structured output.
    # We will simulate the LLM extraction for the sake of the demo,
    # as we don't have an actual API key injected.
    
    # Simple keyword extraction mock
    disaster_type = "Unknown"
    if "earthquake" in raw_report.lower() or "quake" in raw_report.lower():
        disaster_type = "Earthquake"
    elif "flood" in raw_report.lower():
        disaster_type = "Flood"
        
    location = "Unknown"
    if "Los Angeles" in raw_report:
        location = "Los Angeles"
    elif "San Francisco" in raw_report:
        location = "San Francisco"
    elif "Miami" in raw_report:
        location = "Miami"

    needs = []
    if "medics" in raw_report.lower() or "injured" in raw_report.lower():
        needs.append("medics")
    if "water" in raw_report.lower():
        needs.append("water")
    if "boat" in raw_report.lower():
        needs.append("rescue_boats")

    incident = DisasterIncident(
        disaster_type=disaster_type,
        location=location,
        estimated_casualties=5 if "injured" in raw_report.lower() else 0,
        specific_needs=needs,
        raw_report=raw_report
    )
    print(f"[Ingestion Agent] Extracted: {incident.model_dump()}")
    return incident
