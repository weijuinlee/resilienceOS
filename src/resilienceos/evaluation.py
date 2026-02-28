from __future__ import annotations

from statistics import mean
from typing import List

from .models import CouncilReview, PerspectiveScore, ReadinessScores, PlanAction


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_recommendation(
    action: PlanAction,
    assessed_risk: int,
    population_impact: int,
    available_resources: int,
) -> dict:
    """
    Deterministic recommendation score. Replace with model-based scoring later if needed.
    """
    risk_factor = assessed_risk / 100.0
    priority_factor = (6 - action.priority) / 5.0
    urgency = _clamp01(0.35 + 0.50 * risk_factor + 0.15 * priority_factor)

    resource_ratio = min(1.0, available_resources / max(population_impact, 1) / 0.02) if population_impact > 0 else min(1.0, available_resources / 5)
    eta_factor = max(0.0, 1 - action.eta_minutes / 180.0)
    feasibility = _clamp01(0.30 + 0.45 * resource_ratio + 0.25 * eta_factor)

    equity_base = 0.5 if action.targets_vulnerable else 0.35
    equity_bonus = 0.25 if population_impact > 0 else 0.0
    equity_impact = _clamp01(equity_base + equity_bonus)

    efficiency = _clamp01((population_impact / max(action.eta_minutes, 1)) / 20.0)

    return {
        "action": action.what,
        "urgency": urgency,
        "feasibility": feasibility,
        "equity_impact": equity_impact,
        "response_efficiency": efficiency,
    }


def build_council_review(
    command_name: str,
    assessed_risk: int,
    readiness_scores: ReadinessScores | None,
    recommendations: List[dict],
) -> CouncilReview:
    if recommendations:
        urgency = mean(r["urgency"] for r in recommendations)
        feasibility = mean(r["feasibility"] for r in recommendations)
        equity = mean(r["equity_impact"] for r in recommendations)
        efficiency = mean(r["response_efficiency"] for r in recommendations)
    else:
        urgency = feasibility = equity = efficiency = 0.0

    planner_score = _clamp01(0.35 * urgency + 0.30 * feasibility + 0.35 * equity)
    risk_analyst_score = _clamp01(0.50 * (assessed_risk / 100.0) + 0.30 * urgency + 0.20 * (1 - abs(0.8 - feasibility)))
    operations_score = _clamp01(0.45 * feasibility + 0.35 * efficiency + 0.20 * (1 - urgency / 2))

    if readiness_scores is not None:
        community_base = readiness_scores.vulnerable_care / 100.0
        comms_base = readiness_scores.comms / 100.0
    else:
        community_base = 0.45
        comms_base = 0.45

    community_safety_score = _clamp01(0.55 * equity + 0.25 * comms_base + 0.20 * community_base)

    perspectives = [
        PerspectiveScore(
            perspective="planner",
            score=planner_score,
            confidence=0.85,
            rationale=f"Planned actions for {command_name} balance urgency, feasibility, and equity inputs.",
        ),
        PerspectiveScore(
            perspective="risk_analyst",
            score=risk_analyst_score,
            confidence=0.80,
            rationale="Risk score anchors whether pre-impact response needs escalation now versus monitor.",
        ),
        PerspectiveScore(
            perspective="operations",
            score=operations_score,
            confidence=0.78,
            rationale="Operational feasibility estimated from timing, resource pressure, and workload assumptions.",
        ),
        PerspectiveScore(
            perspective="community_safety",
            score=community_safety_score,
            confidence=0.76,
            rationale="Community safety score includes vulnerable-care and local comms readiness factors.",
        ),
    ]

    final_rank = int(_clamp01((planner_score + risk_analyst_score + operations_score + community_safety_score) / 4) * 100)

    score_values = [p.score for p in perspectives]
    if max(score_values) - min(score_values) > 0.25:
        contradiction_summary = (
            "perspectives differ: risk analyst is pushing for stronger readiness while operations may lag due to "
            "resource constraints. Prioritize high-risk routes and vulnerable checks first."
        )
    else:
        contradiction_summary = "council agreement: recommendation set is coherent across all perspectives."

    recommendation_map = {
        "assess": "Use highest confidence triggers to update zone-level preparation and send pre-impact brief within 30 minutes.",
        "plan": "Activate 24h/6h/1h plan by this order and confirm local command-room acknowledgement.",
        "drill": "Repeat missed drill steps in next cycle and close compliance gap with a short replay exercise.",
        "inbox": "Escalate confirmed incidents immediately and suppress duplicate low-confidence duplicates.",
        "simulate": "Focus response on the top impact zones and pre-position assets before predicted water arrival.",
    }

    return CouncilReview(
        final_rank=final_rank,
        perspectives=perspectives,
        final_recommendation=recommendation_map.get(command_name, "Review recommendations with operations lead and confirm assumptions."),
        contradiction_summary=contradiction_summary,
    )

