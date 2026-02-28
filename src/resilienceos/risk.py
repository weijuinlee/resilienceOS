from __future__ import annotations

from typing import Dict, List, Tuple

from .models import (
    AssessInput,
    HazardTrigger,
    ReadinessScores,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _zone_population(profile) -> int:
    return max(profile.total_population_estimate, 1)


def _trigger_score(name: str, score: float, reason: str) -> HazardTrigger:
    return HazardTrigger(name=name, score=score, reason=reason)


def compute_risk_and_readiness(payload: AssessInput) -> Tuple[int, List[HazardTrigger], ReadinessScores, float, List[str], List[str]]:
    # Deterministic scoring phase can be replaced with a trained model call in the future.
    profile = payload.neighborhood_profile
    forecast = payload.forecast_summary

    triggers: Dict[str, Dict[str, float | str]] = {}

    rainfall_score = _clamp01(forecast.rainfall_mm / 260.0)
    triggers["rainfall"] = {
        "score": rainfall_score,
        "reason": f"24h rainfall forecast {forecast.rainfall_mm} mm over {forecast.forecast_window_hours}h.",
    }

    tide_score = _clamp01(forecast.tide_level_m / 3.5)
    triggers["tidal"] = {
        "score": tide_score,
        "reason": f"Current tide level {forecast.tide_level_m}m indicates potential backflow.",
    }

    river_score = _clamp01(forecast.river_level_m / 3.5)
    triggers["river"] = {
        "score": river_score,
        "reason": f"River gauge {forecast.river_level_m}m near drainage limits.",
    }

    alert_score = _clamp01(len([a for a in forecast.alerts if a]) / 3.0)
    triggers["alert_pressure"] = {
        "score": alert_score,
        "reason": f"{len(forecast.alerts)} active alerts in merged feeds.",
    }

    complaint_score = _clamp01(forecast.complaint_count / 20.0)
    triggers["drainage_reports"] = {
        "score": complaint_score,
        "reason": f"{forecast.complaint_count} recent complaints about drainage or stagnant water.",
    }

    infra = payload.critical_infrastructure
    offline_infra = sum(1 for item in infra if item.status == "offline")
    degraded_infra = sum(1 for item in infra if item.status == "degraded")
    critical_infra_factor = _clamp01((offline_infra + 0.5 * degraded_infra) / max(len(infra), 1))
    triggers["critical_infrastructure"] = {
        "score": critical_infra_factor,
        "reason": f"{offline_infra} offline and {degraded_infra} degraded critical assets.",
    }

    pop = _zone_population(profile)
    vuln_ratio = payload.vulnerable_population_count / pop
    vulnerability_score = _clamp01((vuln_ratio / 0.15) if vuln_ratio > 0 else 0.0)
    triggers["vulnerable_density"] = {
        "score": vulnerability_score,
        "reason": f"vulnerable population ratio {payload.vulnerable_population_count}/{pop} (~{int(vuln_ratio*100)}%).",
    }

    weighted_risk = (
        rainfall_score * 0.36
        + tide_score * 0.18
        + river_score * 0.12
        + alert_score * 0.12
        + complaint_score * 0.08
        + critical_infra_factor * 0.07
        + vulnerability_score * 0.07
    )

    hazard_time_weight = _clamp01(payload.hazard_window_hours / 36.0)
    adjusted_score = weighted_risk * (0.55 + 0.45 * hazard_time_weight)
    risk_score = int(round(_clamp01(adjusted_score) * 100))

    top_triggers: List[HazardTrigger] = [
        _trigger_score(name.title().replace("_", " "), data["score"], data["reason"])  # type: ignore[index]
        for name, data in sorted(triggers.items(), key=lambda item: item[1]["score"], reverse=True)
    ]

    top_five = top_triggers[:5]

    comm_infra = [item for item in infra if item.type.lower() in {"siren", "radio", "sms_gateway", "public_alert", "community_hub"}]
    warning_score = int(round(100 * min(1.0, 0.25 + 0.25 * len(comm_infra) + 0.15 * (1 - rain_score))))

    evac_infra = [item for item in infra if item.supports_evacuation]
    logistics_score = int(round(100 * min(1.0, 0.35 + 0.2 * len(evac_infra) + 0.45 * (_clamp01(profile.total_households / 800.0)))))

    vuln_infra = [item for item in infra if item.supports_vulnerable_care]
    vuln_score = int(round(100 * min(1.0, 0.3 + 0.2 * len(vuln_infra) + 0.5 * _clamp01(vuln_ratio / 0.2))))

    comms_score = int(round(100 * _clamp01(0.35 + 0.15 * len(comm_infra) + 0.5 * min(1.0, len(forecast.alerts) / 3.0) + 0.0)))

    # This field is partially synthetic until a formal drill ingestion path is attached.
    drills_score = int(round(100 * 0.55))

    readiness = ReadinessScores(
        warning=warning_score,
        logistics=logistics_score,
        vulnerable_care=vuln_score,
        comms=comms_score,
        drills=drills_score,
    )

    confidence = _clamp01(
        0.45
        + 0.30 * min(1.0, len(infra) / 6.0)
        + 0.15 * min(1.0, len(profile.zones) / 6.0)
        + 0.10 * (1 - min(1.0, forecast.forecast_window_hours / 240.0))
    )

    assumptions: List[str] = []
    missing: List[str] = []

    if len(forecast.alerts) == 0:
        assumptions.append("No active alerts in fixture: confidence is reduced and defaults used for early-warning readiness.")
        missing.append("recent warning feed")
    if len(infra) < 3:
        assumptions.append("Limited critical infrastructure inventory provided; fallback scoring weights used.")
        missing.append("full critical infrastructure inventory")
    if forecast.complaint_count == 0:
        assumptions.append("No complaint stream in fixture; complaint trigger defaults to low urgency.")
        missing.append("complaint stream")

    return risk_score, top_five, readiness, confidence, assumptions, missing
