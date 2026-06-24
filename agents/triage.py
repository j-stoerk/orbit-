from pydantic import BaseModel
from .ingestion import DisasterIncident

class TriagedIncident(BaseModel):
    incident: DisasterIncident
    severity_score: str  # Critical, High, Moderate, Low
    urgency_reasoning: str

def run_triage_agent(incident: DisasterIncident) -> TriagedIncident:
    """
    Triage Agent: Evaluates the severity of the incident.
    """
    print(f"[Triage Agent] Evaluating severity for {incident.disaster_type} in {incident.location}")
    
    score = "Moderate"
    reasoning = "Standard protocol applies."
    
    if incident.estimated_casualties > 0:
        score = "Critical"
        reasoning = f"Life-threatening situation with {incident.estimated_casualties} casualties."
    elif incident.disaster_type in ["Earthquake", "Flood"]:
        score = "High"
        reasoning = "Major natural disaster, high risk of infrastructure damage."

    triaged = TriagedIncident(
        incident=incident,
        severity_score=score,
        urgency_reasoning=reasoning
    )
    print(f"[Triage Agent] Assigned Severity: {triaged.severity_score}")
    return triaged
