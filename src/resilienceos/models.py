from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Actionability(BaseModel):
    can_run_offline: bool = True
    estimated_minutes_to_act: int = Field(default=15, ge=0)
    assumptions: List[str] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)
    recommended_owner: str = "local_coordination_team"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ZoneProfile(BaseModel):
    name: str
    households: int = Field(..., ge=0)
    vulnerable_population: int = Field(default=0, ge=0)
    elderly_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    has_elevated_walkway: bool = False
    has_lift_access: bool = True


class NeighborhoodProfile(BaseModel):
    name: str
    zones: List[ZoneProfile]
    floodproofing_notes: str = ""

    @property
    def total_households(self) -> int:
        return sum(zone.households for zone in self.zones)

    @property
    def total_vulnerable(self) -> int:
        if not self.zones:
            return 0
        return sum(zone.vulnerable_population for zone in self.zones)

    @property
    def total_population_estimate(self) -> int:
        # Assumption: average household size is 3.3. Can be replaced by census feed later.
        return int(self.total_households * 3.3)


class ForecastSummary(BaseModel):
    forecast_window_hours: int = Field(..., ge=1, le=240)
    rainfall_mm: float = Field(..., ge=0)
    tide_level_m: float = Field(..., ge=0)
    river_level_m: float = Field(..., ge=0)
    wind_speed_kph: float = Field(default=0.0, ge=0.0)
    alerts: List[str] = Field(default_factory=list)
    complaint_count: int = Field(default=0, ge=0)
    map_snippets: List[str] = Field(default_factory=list)


class CriticalInfrastructure(BaseModel):
    name: str
    type: str
    status: Literal["operational", "degraded", "offline"] = "operational"
    capacity: int = Field(default=0, ge=0)
    zone: Optional[str] = None
    supports_evacuation: bool = False
    supports_vulnerable_care: bool = False


class AssessInput(BaseModel):
    neighborhood_profile: NeighborhoodProfile
    hazard_window_hours: int = Field(..., ge=1, le=240)
    forecast_summary: ForecastSummary
    critical_infrastructure: List[CriticalInfrastructure]
    vulnerable_population_count: int = Field(..., ge=0)


class HazardTrigger(BaseModel):
    name: str
    score: float = Field(..., ge=0.0, le=1.0)
    reason: str


class ReadinessScores(BaseModel):
    warning: int = Field(..., ge=0, le=100)
    logistics: int = Field(..., ge=0, le=100)
    vulnerable_care: int = Field(..., ge=0, le=100)
    comms: int = Field(..., ge=0, le=100)
    drills: int = Field(..., ge=0, le=100)


class PerspectiveScore(BaseModel):
    perspective: str
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str


class CouncilReview(BaseModel):
    final_rank: int = Field(..., ge=0, le=100)
    perspectives: List[PerspectiveScore]
    final_recommendation: str
    contradiction_summary: str = ""


class BaseOutput(BaseModel):
    plugin_version: str = "0.1.0"
    generated_at: str = Field(default_factory=_utc_timestamp)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_references: List[str] = Field(default_factory=list)
    actionability: Actionability


class AssessOutput(BaseOutput):
    risk_score: int = Field(..., ge=0, le=100)
    top_hazard_triggers: List[HazardTrigger]
    readiness_scores: ReadinessScores
    readiness_gap: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    council_review: CouncilReview


class ResourceInventory(BaseModel):
    households: int = Field(default=0, ge=0)
    volunteers: int = Field(default=0, ge=0)
    coordinators: int = Field(default=0, ge=0)
    transport_vehicles: int = Field(default=0, ge=0)
    buses: int = Field(default=0, ge=0)
    boats: int = Field(default=0, ge=0)
    first_aid_teams: int = Field(default=0, ge=0)
    generators: int = Field(default=0, ge=0)


class PlanInput(BaseModel):
    location: str
    assessed_risk: int = Field(..., ge=0, le=100)
    resources: ResourceInventory
    critical_infrastructure: List[CriticalInfrastructure] = Field(default_factory=list)
    target_zones: List[str] = Field(default_factory=list)


class PlanAction(BaseModel):
    horizon: Literal["24h", "6h", "1h"]
    what: str
    who: str
    priority: int = Field(..., ge=1, le=5)
    eta_minutes: int = Field(..., ge=0)
    people_impacted: int = Field(default=0, ge=0)
    targets_vulnerable: bool = False


class TaskAssignment(BaseModel):
    task: str
    owner: str
    what: str
    priority: int = Field(..., ge=1, le=5)
    eta_minutes: int = Field(..., ge=0)


class PlanOutput(BaseOutput):
    assessed_risk: int = Field(..., ge=0, le=100)
    time_horizon_plan: Dict[str, List[PlanAction]]
    task_assignment_matrix: List[TaskAssignment]
    fallback_routes: List[str]
    shelter_suggestions: List[str]
    materials_checklist: List[str]
    council_review: CouncilReview


class DrillInput(BaseModel):
    last_drill_report: Dict[str, Any]
    response_logs: List[Dict[str, Any]]
    community_observations: List[str] = Field(default_factory=list)


class DrillOutput(BaseOutput):
    compliance_score: int = Field(..., ge=0, le=100)
    missed_steps: List[str]
    corrected_procedures: List[str]
    next_drill_template: List[str]
    council_review: CouncilReview


class SocialSnippet(BaseModel):
    text: str
    media_links: List[str] = Field(default_factory=list)
    severity_tag: Optional[str] = None


class IncidentCard(BaseModel):
    incident_id: str
    cluster: str
    text: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    media_count: int = Field(default=0, ge=0)
    severity: str = "medium"
    suggested_owner: str = "community_coordinator"


class EscalationDecision(BaseModel):
    incident_id: str
    decision: str
    reasoning: str


class InboxInput(BaseModel):
    social_media_snippets: List[SocialSnippet]
    severity_tags: List[str] = Field(default_factory=list)


class InboxOutput(BaseOutput):
    incident_clusters: Dict[str, int]
    confidence_ranked_incident_cards: List[IncidentCard]
    escalation_decisions: List[EscalationDecision]
    council_review: CouncilReview


class ExplainInput(BaseModel):
    generated_plan: Dict[str, Any]
    audience: str = "public_official"


class ExplainOutput(BaseOutput):
    plain_language_rationale: str
    evidence_references: List[str]
    assumptions: List[str]
    missing_data: List[str]


class SegmentForecast(BaseModel):
    name: str
    population: int = Field(..., ge=0)
    elevation_m: float = Field(..., ge=0)
    vulnerable_ratio: float = Field(..., ge=0.0, le=1.0)
    mobility_score: float = Field(..., ge=0.0, le=1.0)
    critical_facility_density: float = Field(default=0.0, ge=0.0, le=1.0)


class SimulateInput(BaseModel):
    scenario_name: str
    hazard_window_hours: int = Field(..., ge=1, le=240)
    forecast_summary: ForecastSummary
    neighborhood_segments: List[SegmentForecast]
    prepositioned_resources: Optional[ResourceInventory] = None


class ImpactSegment(BaseModel):
    segment: str
    estimated_people_impacted: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    action_need_rank: int = Field(..., ge=1)


class SimulateOutput(BaseOutput):
    predicted_impact_by_segment: List[ImpactSegment]
    recommended_preemptive_actions: List[PlanAction]
    first_60_minute_actions: List[PlanAction]
    council_review: CouncilReview
