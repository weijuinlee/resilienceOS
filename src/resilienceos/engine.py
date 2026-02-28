from __future__ import annotations

from typing import Any, Dict, List

from .evaluation import build_council_review, score_recommendation
from .models import (
    Actionability,
    AgentOutput,
    AssessInput,
    AssessOutput,
    IncidentCard,
    EscalationDecision,
    DrillInput,
    DrillOutput,
    BaseOutput,
    ExplainInput,
    ExplainOutput,
    HazardTrigger,
    InboxInput,
    InboxOutput,
    PlanAction,
    PlanInput,
    PlanOutput,
    SimulateInput,
    SimulateOutput,
    ImpactSegment,
    SocialSnippet,
    TaskAssignment,
)
from .risk import compute_risk_and_readiness


def _build_actionability(
    minutes: int,
    assumptions: List[str],
    missing: List[str],
    owner: str = "local_coordination_team",
    can_run_offline: bool = True,
) -> Actionability:
    return Actionability(
        can_run_offline=can_run_offline,
        estimated_minutes_to_act=minutes,
        assumptions=assumptions,
        missing_data=missing,
        recommended_owner=owner,
    )


def _merge_evidence(*items: Any) -> List[str]:
    refs = []
    for item in items:
        if not item:
            continue
        if isinstance(item, str):
            refs.append(item)
        else:
            refs.append(str(item))
    return refs[:6]


def assess(payload: AssessInput) -> AssessOutput:
    risk_score, triggers, readiness, confidence, assumptions, missing = compute_risk_and_readiness(payload)

    if len(triggers) < 5:
        filler = [
            HazardTrigger(name="data_gap", score=0.0, reason="Not enough feed data to generate more triggers."),
        ]
        triggers.extend(filler * (5 - len(triggers)))

    readiness_gap = []
    if readiness.warning < 70:
        readiness_gap.append("warning")
    if readiness.logistics < 70:
        readiness_gap.append("logistics")
    if readiness.vulnerable_care < 70:
        readiness_gap.append("vulnerable_care")
    if readiness.comms < 70:
        readiness_gap.append("comms")

    council = build_council_review(
        command_name="assess",
        assessed_risk=risk_score,
        readiness_scores=readiness,
        recommendations=[
            {
                "urgency": risk_score / 100,
                "feasibility": readiness.logistics / 100,
                "equity_impact": readiness.vulnerable_care / 100,
                "response_efficiency": 0.5,
            }
        ],
    )

    return AssessOutput(
        risk_score=risk_score,
        top_hazard_triggers=triggers[:5],
        readiness_scores=readiness,
        readiness_gap=", ".join(readiness_gap) if readiness_gap else None,
        assumptions=assumptions,
        council_review=council,
        confidence=confidence,
        evidence_references=_merge_evidence(
            payload.neighborhood_profile.name,
            payload.forecast_summary.alerts,
            payload.critical_infrastructure,
        ),
        actionability=_build_actionability(
            minutes=15,
            assumptions=assumptions,
            missing=missing,
            owner="neighborhood_ops_cell",
        ),
    )


def _zone_names(payload: PlanInput) -> List[str]:
    return payload.target_zones if payload.target_zones else [payload.location]


def _base_plan_actions(assessed_risk: int, zones: List[str]) -> Dict[str, List[PlanAction]]:
    zone_tag = ", ".join(zones)
    high_risk = assessed_risk >= 75
    medium_risk = 50 <= assessed_risk < 75

    actions: Dict[str, List[PlanAction]] = {
        "24h": [
            PlanAction(
                horizon="24h",
                what="Validate weather, tide, and river dashboards; publish watch state with 2 checkpoints.",
                who="ops_lead",
                priority=3,
                eta_minutes=120,
                people_impacted=0,
                targets_vulnerable=True,
            ),
            PlanAction(
                horizon="24h",
                what=f"Inspect primary drains and place temporary barriers at choke points in {zone_tag}.",
                who="infrastructure_team",
                priority=2 if high_risk else 3,
                eta_minutes=300,
                people_impacted=90,
                targets_vulnerable=False,
            ),
        ],
        "6h": [
            PlanAction(
                horizon="6h",
                what="Confirm household contact trees and text tree readiness; prepare multilingual advisory in EN/中文/Melayu/Tamil.",
                who="comm_hub",
                priority=2,
                eta_minutes=180,
                people_impacted=150,
                targets_vulnerable=True,
            ),
            PlanAction(
                horizon="6h",
                what=f"Pre-position equipment and shelters for low-lying blocks in {zone_tag}.",
                who="logistics_unit",
                priority=2 if high_risk else 4,
                eta_minutes=360,
                people_impacted=220,
                targets_vulnerable=True,
            ),
        ],
        "1h": [
            PlanAction(
                horizon="1h",
                what="Prepare evacuation points and route leaders with printed maps at command room and schools.",
                who="coordination_team",
                priority=1,
                eta_minutes=45,
                people_impacted=180,
                targets_vulnerable=True,
            ),
            PlanAction(
                horizon="1h",
                what="Finalize check-in process for vulnerable households and welfare checks.",
                who="vulnerable_care_team",
                priority=2,
                eta_minutes=60,
                people_impacted=0,
                targets_vulnerable=True,
            ),
        ],
    }

    if medium_risk:
        actions["24h"].append(
            PlanAction(
                horizon="24h",
                what=f"Run one communication drill for multilingual messaging in {zone_tag}.",
                who="community_outreach",
                priority=4,
                eta_minutes=90,
                people_impacted=0,
                targets_vulnerable=False,
            )
        )

    if high_risk:
        actions["6h"].append(
            PlanAction(
                horizon="6h",
                what="Request standby rescue support and activate shelters at two redundancy levels.",
                who="neighborhood_coordinator",
                priority=1,
                eta_minutes=210,
                people_impacted=320,
                targets_vulnerable=True,
            )
        )
        actions["1h"].append(
            PlanAction(
                horizon="1h",
                what="Suspend non-essential road works and block flood-prone lanes.",
                who="traffic_unit",
                priority=1,
                eta_minutes=20,
                people_impacted=0,
                targets_vulnerable=False,
            )
        )

    return actions


def _build_matrix(actions: List[PlanAction]) -> List[TaskAssignment]:
    matrix: List[TaskAssignment] = []
    for action in actions:
        matrix.append(
            TaskAssignment(
                task=action.what,
                owner=action.who,
                what=f"{action.who.replace('_', ' ').title()} owns and checks completion.",
                priority=action.priority,
                eta_minutes=action.eta_minutes,
            )
        )
    return matrix


def _extract_routes_and_shelters(payload: PlanInput):
    shelter_suggestions = []
    fallback_routes = []
    for item in payload.critical_infrastructure:
        if item.type == "shelter" or item.type == "community_hub":
            shelter_suggestions.append(item.name)
        if item.supports_evacuation:
            fallback_routes.append(item.name)

    if not shelter_suggestions:
        shelter_suggestions = ["Municipal hall", "Primary school gym", "Community sports hall"]
    if not fallback_routes:
        fallback_routes = ["Ring road via North Gate", "Canal road via East Lift lane"]

    return fallback_routes[:4], shelter_suggestions[:4]


def plan(payload: PlanInput) -> PlanOutput:
    zones = _zone_names(payload)
    actions_by_horizon = _base_plan_actions(payload.assessed_risk, zones)
    flat_actions = [item for bucket in actions_by_horizon.values() for item in bucket]

    resource_count = sum(payload.resources.dict().values())
    scores = [
        score_recommendation(a, payload.assessed_risk, max(a.people_impacted, max(1, payload.assessed_risk)), resource_count)
        for a in flat_actions
    ]

    council = build_council_review(
        command_name="plan",
        assessed_risk=payload.assessed_risk,
        readiness_scores=None,
        recommendations=scores,
    )

    fallback_routes, shelter_suggestions = _extract_routes_and_shelters(payload)

    materials_checklist = [
        "sandbags",
        "flood tags",
        "portable radios",
        "torch and batteries",
        "water and food packets",
        "welfare check forms",
        "evacuation map printouts",
    ]

    matrix = _build_matrix(flat_actions)

    assumptions: List[str] = []
    missing: List[str] = []
    if resource_count < 5:
        missing.append("resource inventory completeness")
        assumptions.append("Inventory is thin; fallback operational assets are assumed and logged.)")

    confidence = 0.86 if resource_count >= 5 else 0.7

    return PlanOutput(
        assessed_risk=payload.assessed_risk,
        time_horizon_plan=actions_by_horizon,
        task_assignment_matrix=matrix,
        fallback_routes=fallback_routes,
        shelter_suggestions=shelter_suggestions,
        materials_checklist=materials_checklist,
        council_review=council,
        confidence=confidence,
        evidence_references=_merge_evidence(
            payload.location,
            payload.assessed_risk,
            payload.resources,
        ),
        actionability=_build_actionability(
            minutes=20,
            assumptions=assumptions,
            missing=missing,
            owner="incident_commander",
        ),
    )


MANDATORY_DRILL_STEPS = [
    "Issue alert to residents",
    "Verify evacuation routes",
    "Check volunteer roster",
    "Confirm shelter capacity",
    "Record welfare check on vulnerable households",
]


def drill(payload: DrillInput) -> DrillOutput:
    steps_completed = {str(step).strip().lower() for step in payload.last_drill_report.get("steps_completed", [])}
    observed = {obs.lower() for obs in payload.last_drill_report.get("observed_steps", [])}
    observed.update({str(log.get("event", "")).strip().lower() for log in payload.response_logs})

    missed_steps: List[str] = []
    for required in MANDATORY_DRILL_STEPS:
        if required.lower() not in steps_completed and required.lower() not in observed:
            missed_steps.append(required)

    compliance = int(round((1 - len(missed_steps) / len(MANDATORY_DRILL_STEPS)) * 100))

    corrected = [f"Add protocol: {step}." for step in missed_steps]

    next_template = [
        "Run short tabletop review in 2 weeks.",
        "Use multilingual role-cards in comms and check-in training.",
        "Assign two alternate coordinators per shift.",
        "Capture timestamped logs for every escalation decision.",
    ]

    scores = [
        {
            "urgency": 0.4 if compliance >= 60 else 0.7,
            "feasibility": 0.6,
            "equity_impact": 0.7,
            "response_efficiency": 0.5,
        }
    ]

    council = build_council_review(
        command_name="drill",
        assessed_risk=70,
        readiness_scores=None,
        recommendations=scores,
    )

    assumptions = []
    missing = []
    if not payload.response_logs:
        missing.append("time-stamped response log")
        assumptions.append("No response logs provided; compliance is checklist-based only.")

    return DrillOutput(
        compliance_score=compliance,
        missed_steps=missed_steps,
        corrected_procedures=corrected,
        next_drill_template=next_template,
        council_review=council,
        confidence=0.9 if payload.response_logs else 0.7,
        evidence_references=_merge_evidence(
            payload.last_drill_report,
            payload.response_logs,
            payload.community_observations,
        ),
        actionability=_build_actionability(
            minutes=5,
            assumptions=assumptions,
            missing=missing,
            owner="training_officer",
        ),
    )


CLUSTER_KEYWORDS = {
    "drainage_blockage": ["drain", "clog", "blocked", "waterlogging", "flooding"],
    "evacuation_request": ["stranded", "evacu", "move", "evac", "rescue"],
    "infrastructure_failure": ["road", "bridge", "pump", "transformer", "power", "electric"],
    "shelter_capacity": ["shelter", "venue", "place", "space", "bed"],
    "medical": ["injury", "medic", "ambulance", "wound", "first aid"],
}


def _severity_to_bias(tag: str | None) -> float:
    if not tag:
        return 0.55
    t = tag.lower()
    if t in {"high", "critical", "urgent"}:
        return 0.9
    if t in {"medium", "warn", "warning"}:
        return 0.75
    return 0.6


def _match_cluster(snippet: SocialSnippet) -> tuple[str, float]:
    text = snippet.text.lower()
    best_cluster = "unverified_report"
    best_score = 0.0

    for cluster, tokens in CLUSTER_KEYWORDS.items():
        score = 0.0
        for token in tokens:
            if token in text:
                score += 0.2
        if score > best_score:
            best_score = score
            best_cluster = cluster

    confidence = max(0.3, min(1.0, best_score + 0.45 + 0.1 * len(snippet.media_links)))
    if snippet.severity_tag:
        confidence = min(1.0, confidence + (_severity_to_bias(snippet.severity_tag) - 0.55) * 0.5)

    return best_cluster, confidence


def inbox(payload: InboxInput) -> InboxOutput:
    clusters: Dict[str, int] = {}
    cards: List[IncidentCard] = []

    for idx, snippet in enumerate(payload.social_media_snippets, start=1):
        cluster, conf = _match_cluster(snippet)
        clusters[cluster] = clusters.get(cluster, 0) + 1
        cards.append(
            IncidentCard(
                incident_id=f"INC-{idx:03d}",
                cluster=cluster,
                text=snippet.text,
                confidence=conf,
                media_count=len(snippet.media_links),
                severity=snippet.severity_tag or "medium",
                suggested_owner="local_coordination_hub",
            )
        )

    cards.sort(key=lambda card: card.confidence, reverse=True)

    decisions: List[EscalationDecision] = []
    for card in cards:
        if card.confidence >= 0.85:
            decision = "escalate_to_emergency_services"
            reason = "High confidence with corroborating media evidence. Immediate verification and field dispatch recommended."
        elif card.confidence >= 0.65:
            decision = "alert_local_coordinator"
            reason = "Moderate confidence. Verify using neighborhood hub and assign one owner."
        else:
            decision = "monitor_and_aggregate"
            reason = "Low confidence. Keep for correlation with additional messages before deployment."

        decisions.append(EscalationDecision(incident_id=card.incident_id, decision=decision, reasoning=reason))

    scores = [
        {
            "urgency": min(0.95, card.confidence + 0.05),
            "feasibility": 0.65,
            "equity_impact": 0.65,
            "response_efficiency": 0.5,
        }
        for card in cards
    ]

    council = build_council_review(
        command_name="inbox",
        assessed_risk=72,
        readiness_scores=None,
        recommendations=scores,
    )

    assumptions = []
    missing = []
    if not payload.social_media_snippets:
        missing.append("social signals")
        assumptions.append("No snippets provided; no incident cards can be produced from live feeds.")

    return InboxOutput(
        incident_clusters=clusters,
        confidence_ranked_incident_cards=cards,
        escalation_decisions=decisions,
        council_review=council,
        confidence=0.8,
        evidence_references=["social snippets", "media links", "severity tags"],
        actionability=_build_actionability(
            minutes=8,
            assumptions=assumptions,
            missing=missing,
            owner="community_hub",
        ),
    )


def explain(payload: ExplainInput) -> ExplainOutput:
    plan = payload.generated_plan
    keys = sorted(plan.keys()) if isinstance(plan, dict) else ["unknown"]

    assumptions = []
    missing = []
    if "confidence" not in plan:
        assumptions.append("generated plan does not include explicit model confidence.")
    if "evidence_references" not in plan:
        missing.append("source references")

    rationale = [
        "Priorities are ordered as 24h, 6h, and 1h checkpoints to support pre-impact sequencing.",
        "Actions were generated by deterministic rules from risk, readiness, and resource assumptions.",
    ]
    if "risk_score" in plan:
        rationale.append(f"Risk score {plan.get('risk_score')} shifts the urgency tiering in the selected plan.")
    if "council_review" in plan:
        rationale.append("Council review score is included so leads can compare planner, operations, and safety perspectives.")

    return ExplainOutput(
        plain_language_rationale=" ".join(rationale),
        evidence_references=keys,
        assumptions=assumptions,
        missing_data=missing,
        confidence=0.82,
        actionability=_build_actionability(
            minutes=2,
            assumptions=assumptions,
            missing=missing,
            owner="explainability_team",
        ),
    )


def _impact_score(segment: Any, forecast: Any, resource_factor: float) -> float:
    base = (
        0.42 * (forecast.rainfall_mm / 260.0)
        + 0.25 * (forecast.tide_level_m / 3.5)
        + 0.20 * (forecast.river_level_m / 3.0)
        + 0.13 * min(1.0, len(forecast.alerts) / 3.0)
    )
    elevation_penalty = max(0.0, 1.0 - (segment.elevation_m / 12.0))
    vuln_factor = 0.6 + segment.vulnerable_ratio
    mobility_penalty = 1.0 - (segment.mobility_score * 0.5)
    return min(1.0, base * (0.45 + elevation_penalty) * vuln_factor * mobility_penalty * resource_factor)


def simulate(payload: SimulateInput) -> SimulateOutput:
    resource_factor = 1.0
    if payload.prepositioned_resources:
        pool = sum(payload.prepositioned_resources.dict().values())
        if pool <= 4:
            resource_factor = 0.85
        elif pool >= 12:
            resource_factor = 1.0

    ranked = []
    for seg in payload.neighborhood_segments:
        score = _impact_score(seg, payload.forecast_summary, resource_factor)
        people_impacted = int(seg.population * score * 0.9)
        ranked.append((score, seg, people_impacted))

    ranked.sort(reverse=True, key=lambda item: item[0])

    impacts: List[ImpactSegment] = []
    for idx, (impact_ratio, seg, people_impacted) in enumerate(ranked, start=1):
        impacts.append(
            ImpactSegment(
                segment=seg.name,
                estimated_people_impacted=people_impacted,
                confidence=min(0.95, max(0.4, impact_ratio + 0.15)),
                action_need_rank=idx,
            )
        )

    top_segment = impacts[0].estimated_people_impacted if impacts else 0
    preemptive = [
        PlanAction(
            horizon="24h",
            what="Move rescue and welfare teams to highest impact segment before floodfront reaches it.",
            who="rescue_team",
            priority=1,
            eta_minutes=120,
            people_impacted=top_segment,
            targets_vulnerable=True,
        ),
        PlanAction(
            horizon="24h",
            what="Stage shelter stocks for low-elevation blocks with multilingual reception desks.",
            who="shelter_ops",
            priority=2,
            eta_minutes=180,
            people_impacted=top_segment,
            targets_vulnerable=True,
        ),
    ]

    first_60 = [
        PlanAction(
            horizon="1h",
            what="Activate command room and publish 60-minute action script.",
            who="ops_lead",
            priority=1,
            eta_minutes=10,
            people_impacted=80,
            targets_vulnerable=True,
        ),
        PlanAction(
            horizon="1h",
            what="Dispatch route inspection teams to top three roads on the live map.",
            who="routing_unit",
            priority=1,
            eta_minutes=25,
            people_impacted=40,
            targets_vulnerable=False,
        ),
    ]

    avg_people = int(sum(item.estimated_people_impacted for item in impacts) / max(1, len(impacts))) if impacts else 1
    scores = [
        score_recommendation(act, max(1, 100 - int(payload.hazard_window_hours)), act.people_impacted, avg_people)
        for act in preemptive + first_60
    ]

    council = build_council_review(
        command_name="simulate",
        assessed_risk=85,
        readiness_scores=None,
        recommendations=scores,
    )

    return SimulateOutput(
        predicted_impact_by_segment=impacts,
        recommended_preemptive_actions=preemptive,
        first_60_minute_actions=first_60,
        council_review=council,
        confidence=0.78,
        evidence_references=_merge_evidence(
            payload.scenario_name,
            payload.forecast_summary.alerts,
        ),
        actionability=_build_actionability(
            minutes=30,
            assumptions=["Simulation assumes linear runoff and no second-event peak in first 6h."],
            missing=["building-level flooding model calibration"],
            owner="simulation_owner",
        ),
    )


def _combine_actionability(outputs: List[BaseOutput]) -> Actionability:
    actionabilities = [output.actionability for output in outputs if output is not None]
    if not actionabilities:
        return _build_actionability(
            minutes=20,
            assumptions=["No concrete command output to combine."],
            missing=["agent_inputs"],
            owner="incident_commander",
        )

    assumptions: List[str] = []
    missing: List[str] = []
    minutes = max(item.estimated_minutes_to_act for item in actionabilities)
    can_run_offline = all(item.can_run_offline for item in actionabilities)
    owner = actionabilities[0].recommended_owner

    for item in actionabilities:
        assumptions.extend(item.assumptions)
        missing.extend(item.missing_data)
        if item.recommended_owner != owner:
            owner = f"{owner}/{item.recommended_owner}"

    assumption_seen = set()
    assumptions = [x for x in assumptions if not (x in assumption_seen or assumption_seen.add(x))]

    missing_seen = set()
    missing = [x for x in missing if not (x in missing_seen or missing_seen.add(x))]

    return _build_actionability(
        minutes=minutes,
        assumptions=assumptions,
        missing=missing,
        owner=owner,
        can_run_offline=can_run_offline,
    )


def agent(
    assess_payload: AssessInput,
    plan_payload: PlanInput,
    include_inbox: InboxInput | None = None,
    include_simulate: SimulateInput | None = None,
) -> AgentOutput:
    assess_result = assess(assess_payload)
    plan_result = plan(plan_payload)

    included_modules = ["assess", "plan"]
    inbox_result = None
    simulate_result = None
    actionability_sources = [assess_result, plan_result]

    if include_inbox is not None:
        included_modules.append("inbox")
        inbox_result = inbox(include_inbox)
        actionability_sources.append(inbox_result)

    if include_simulate is not None:
        included_modules.append("simulate")
        simulate_result = simulate(include_simulate)
        actionability_sources.append(simulate_result)

    confidence = assess_result.confidence
    if plan_result.confidence < confidence:
        confidence = plan_result.confidence
    if inbox_result and inbox_result.confidence < confidence:
        confidence = inbox_result.confidence
    if simulate_result and simulate_result.confidence < confidence:
        confidence = simulate_result.confidence

    immediate_actions = [
        f"{item.owner}: {item.task} (ETA {item.eta_minutes}m)"
        for item in sorted(plan_result.task_assignment_matrix, key=lambda item: (item.priority, item.eta_minutes))[:6]
    ]

    watchlist = []
    if assess_result.readiness_gap:
        watchlist.append(f"Readiness gaps to resolve: {assess_result.readiness_gap}")
    if assess_result.assumptions:
        watchlist.append("Assess assumptions: " + ", ".join(assess_result.assumptions))
    if plan_result.actionability.missing_data:
        watchlist.append("Plan missing data: " + ", ".join(plan_result.actionability.missing_data))
    if include_inbox and inbox_result and any(
        item.confidence >= 0.85 for item in inbox_result.confidence_ranked_incident_cards
    ):
        watchlist.append("High-confidence incidents require active escalation routing.")
    if include_simulate and simulate_result and simulate_result.predicted_impact_by_segment:
        top_segment = simulate_result.predicted_impact_by_segment[0].segment
        watchlist.append(f"Monitor highest-impact segment first: {top_segment}")

    if not watchlist:
        watchlist.append("No immediate risks beyond standard protocol.")

    return AgentOutput(
        scenario=assess_payload.neighborhood_profile.name,
        mission="Adaptive neighborhood resilience guidance across assess/plan/monitor loops.",
        included_modules=included_modules,
        assessed_risk=assess_result.risk_score,
        readiness_gap=assess_result.readiness_gap,
        immediate_actions=immediate_actions,
        watchlist=watchlist,
        assess=assess_result,
        plan=plan_result,
        inbox=inbox_result,
        simulate=simulate_result,
        confidence=confidence,
        evidence_references=_merge_evidence(
            assess_payload.neighborhood_profile.name,
            assess_result.risk_score,
            plan_result.assessed_risk,
            assess_payload.forecast_summary.alerts,
        ),
        actionability=_combine_actionability(actionability_sources),
    )
