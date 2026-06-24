"""Shared Pydantic models for the Crisis Coordinator platform."""
from __future__ import annotations
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import datetime as _dt
import uuid


def _now() -> str:
    return _dt.datetime.utcnow().isoformat() + "Z"


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class GeoPoint(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None


class DisasterIncident(BaseModel):
    """Structured incident produced by the Ingestion Agent.
    Population figures are Optional — None means "not stated / unknown" (never
    fabricated)."""
    disaster_type: str = "Unknown"
    location: str = "Unknown"
    coordinates: GeoPoint = Field(default_factory=GeoPoint)
    estimated_affected: Optional[int] = None
    estimated_casualties: Optional[int] = None
    specific_needs: List[str] = Field(default_factory=list)
    raw_report: str = ""


class SectorNeed(BaseModel):
    sector: str
    priority: str           # Critical | High | Moderate
    rationale: str
    indicators: List[str] = Field(default_factory=list)


class Assessment(BaseModel):
    """MIRA-style rapid multi-sector needs assessment (UNDAC F.2 / G).
    All population figures are Optional and carry a label + sources; None means
    "not estimated" rather than an invented number."""
    severity_score: str                     # Critical | High | Moderate | Low
    severity_index: int = 0                 # 0-100
    severity_basis: str = ""                # what the rating is grounded in
    urgency_reasoning: str = ""
    affected_population: Optional[int] = None
    affected_label: str = ""
    displaced_estimate: Optional[int] = None
    displaced_label: str = ""
    fatalities_estimate: Optional[int] = None
    fatalities_label: str = ""
    alert_level: Optional[str] = None       # GDACS/PAGER alert when available
    exposure_available: bool = False
    data_sources: List[Dict[str, str]] = Field(default_factory=list)
    secondary_hazards: List[str] = Field(default_factory=list)
    sector_needs: List[SectorNeed] = Field(default_factory=list)
    priority_actions: List[str] = Field(default_factory=list)
    hazard_ref: str = ""                    # handbook K.x reference
    golden_hours: int = 72


class Ack(BaseModel):
    """Human acknowledgement of a machine proposal."""
    status: str = "Proposed"      # Proposed | Accepted | Rejected | Amended
    by: str = ""
    note: str = ""
    at: Optional[str] = None


class Evidence(BaseModel):
    """A single piece of evidence underpinning the picture (for explainability)."""
    id: str = Field(default_factory=_new_id)
    source: str                    # USGS, GDACS, Google News, Mastodon, OSM, Open-Meteo, Model
    kind: str                      # feed | news | social | context | model
    statement: str                 # what this evidence asserts
    url: Optional[str] = None
    time: Optional[str] = None


class Confidence(BaseModel):
    """Confidence is SEPARATE from severity: how well-corroborated the picture is."""
    level: str = "Unverified"      # Confirmed | Probable | Unverified
    score: int = 0                 # 0-100
    corroborating_sources: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class OpenQuestion(BaseModel):
    """A MIRA-style unanswered question that must be resolved."""
    id: str = Field(default_factory=_new_id)
    question: str
    category: str = "impact"       # impact | access | sector | capacity
    why: str = ""
    status: str = "Open"           # Open | Answered
    answer: str = ""


class Comment(BaseModel):
    id: str = Field(default_factory=_new_id)
    at: str = Field(default_factory=_now)
    author: str = "operator"
    text: str = ""


class Decision(BaseModel):
    id: str = Field(default_factory=_new_id)
    at: str = Field(default_factory=_now)
    author: str = "operator"
    decision: str = ""
    rationale: str = ""


class ThreeWEntry(BaseModel):
    """A single row of the 3W matrix (Who does What, Where) — a machine proposal
    that a human can accept / reject / amend."""
    id: str = Field(default_factory=_new_id)
    who: str                # actor / cluster lead
    what: str               # activity
    where: str              # location / sector
    sector: str
    status: str = "Planned"  # Planned | Ongoing | Gap
    rationale: str = ""      # evidence-first: why this cluster is engaged
    ack: Ack = Field(default_factory=Ack)


class CoordinationPlan(BaseModel):
    """Output of the Coordination Agent (OSOCC D.3 / G.6)."""
    osocc_activated: bool = True
    lead_clusters: List[str] = Field(default_factory=list)
    three_w: List[ThreeWEntry] = Field(default_factory=list)
    coordination_gaps: List[str] = Field(default_factory=list)
    tasking: List[str] = Field(default_factory=list)


class ResourceLine(BaseModel):
    item: str
    label: str = ""
    unit: str = "units"
    available: int = 0                  # real current stock across locations
    locations: List[str] = Field(default_factory=list)
    requested: Optional[int] = None     # None = no basis to quantify (not invented)
    allocated: int = 0
    gap: Optional[int] = None
    status: str = ""                    # Filled | Partial | Unmet | In stock


class LogisticsPlan(BaseModel):
    """Output of the Logistics Agent (UNDAC G.11)."""
    lines: List[ResourceLine] = Field(default_factory=list)
    total_gap_items: int = 0
    summary: str = ""
    procurement_recommendations: List[str] = Field(default_factory=list)


class Notification(BaseModel):
    """Everbridge-style mass notification / alert."""
    id: str = Field(default_factory=_new_id)
    severity: str
    channel: List[str] = Field(default_factory=list)   # SMS, Email, Push, Radio
    audience: List[str] = Field(default_factory=list)   # responder groups
    headline: str = ""
    body: str = ""
    issued_at: str = Field(default_factory=_now)
    requires_ack: bool = False
    ack: Ack = Field(default_factory=Ack)


class SitRep(BaseModel):
    """Situation Report — signature UNDAC IM product (F.3)."""
    number: int = 1
    title: str = ""
    issued_at: str = Field(default_factory=_now)
    headline: str = ""
    body_markdown: str = ""


class Incident(BaseModel):
    """The aggregate record threaded through the OSOCC workflow."""
    id: str = Field(default_factory=_new_id)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    status: str = "New"     # New | Assessing | Coordinating | Dispatched | Closed
    incident: DisasterIncident
    assessment: Optional[Assessment] = None
    coordination: Optional[CoordinationPlan] = None
    logistics: Optional[LogisticsPlan] = None
    sitrep: Optional[SitRep] = None
    notifications: List[Notification] = Field(default_factory=list)
    # explainability & uncertainty
    confidence: Optional[Confidence] = None
    evidence: List[Evidence] = Field(default_factory=list)
    open_questions: List[OpenQuestion] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    # collaboration
    comments: List[Comment] = Field(default_factory=list)
    decisions: List[Decision] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    approved: Optional[bool] = None

    def log(self, agent: str, message: str, payload: Optional[dict] = None):
        self.timeline.append({
            "at": _now(), "agent": agent, "message": message, "payload": payload or {},
        })
        self.updated_at = _now()
