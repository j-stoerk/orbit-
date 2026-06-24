"""
Alert & Notification Agent (Everbridge-style mass notification).

Generates severity-driven critical-event notifications targeted at the right
responder audiences over the right channels, with escalation and acknowledgement
rules. This mirrors Everbridge Critical Event Management: detect → assess →
notify the right people → require acknowledgement.

UNDAC mapping: A.2 Humanitarian response mechanisms (alerting/mobilisation);
E.2 Safety & security notifications; F.4 Media/public information.
"""
from __future__ import annotations

from ..models import DisasterIncident, Assessment, Notification

# Audience routing by severity (who gets mobilised)
_AUDIENCE_BY_SEVERITY = {
    "Critical": ["UNDAC Team", "USAR/INSARAG", "EMT (Medical Teams)", "OCHA ERS",
                 "National Authorities (NDMA)", "Logistics Cluster", "All Field Responders"],
    "High": ["UNDAC Team", "Relevant Clusters", "National Authorities (NDMA)",
             "OCHA Regional Office"],
    "Moderate": ["UNDAC Team", "Relevant Clusters"],
    "Low": ["Duty Officer"],
}

_CHANNELS_BY_SEVERITY = {
    "Critical": ["SMS", "Voice", "Push", "Email", "Satellite Radio"],
    "High": ["SMS", "Push", "Email"],
    "Moderate": ["Push", "Email"],
    "Low": ["Email"],
}


def run_alert_agent(incident: DisasterIncident, assessment: Assessment,
                    emit=None) -> list[Notification]:
    def say(msg):
        if emit:
            emit("Alerts", msg)

    sev = assessment.severity_score
    audiences = _AUDIENCE_BY_SEVERITY.get(sev, ["Duty Officer"])
    channels = _CHANNELS_BY_SEVERITY.get(sev, ["Email"])
    requires_ack = sev in ("Critical", "High")

    say(f"Composing {sev} critical-event notification → {len(audiences)} audiences "
        f"over {len(channels)} channels.")

    loc = incident.location or "affected area"
    if assessment.affected_population is not None:
        impact = f"Estimated {assessment.affected_population:,} affected"
        if assessment.displaced_estimate is not None:
            impact += f", {assessment.displaced_estimate:,} displaced"
        impact += ". "
    else:
        impact = "Impact figures being assessed. "
    headline = f"[{sev.upper()}] {incident.disaster_type} — {loc}: response mobilisation"
    body = (
        f"A {sev.lower()}-severity {incident.disaster_type} is impacting {loc}. "
        + impact
        + f"Priority: {assessment.priority_actions[0] if assessment.priority_actions else 'mobilise response'}. "
        + ("ACKNOWLEDGEMENT REQUIRED." if requires_ack else "")
    )

    primary = Notification(
        severity=sev, channel=channels, audience=audiences,
        headline=headline, body=body, requires_ack=requires_ack,
    )

    notifications = [primary]

    # Escalation: for Critical events, add a public-information advisory
    if sev == "Critical":
        notifications.append(Notification(
            severity=sev,
            channel=["Public Web", "Media", "SMS Cell-Broadcast"],
            audience=["Affected Population", "Media"],
            headline=f"PUBLIC ADVISORY: {incident.disaster_type} in {loc}",
            body=("Follow instructions from local authorities. "
                  + (f"Secondary hazards possible: {', '.join(assessment.secondary_hazards[:3])}."
                     if assessment.secondary_hazards else "")),
            requires_ack=False,
        ))
        say("Critical event — escalation: public advisory queued for cell-broadcast.")

    say(f"{len(notifications)} notification(s) issued; ack required = {requires_ack}.")
    return notifications
