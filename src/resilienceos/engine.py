from __future__ import annotations

import os
import json
import sys
import re
import urllib.error
import urllib.request
from pathlib import Path
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


def _read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if "#" in line:
                line = line.split("#", 1)[0].rstrip()

            if line.lower().startswith("export "):
                line = line[7:].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip().strip("\"").strip("'")

            if key:
                values[key] = value
    except OSError:
        return {}
    return values


def _candidate_env_files() -> List[Path]:
    candidates: List[Path] = []
    custom = os.getenv("RESILIENCEOS_OPENAI_ENV_FILE")
    if custom:
        candidates.append(Path(custom))
    else:
        candidates.extend(
            [
                Path(".env.openai"),
                Path(".env"),
                Path(".env.local"),
                Path(".env.openai.local"),
                Path(".env.openai.dev"),
            ]
        )

    repo_root = Path(__file__).resolve().parents[2]
    repo_candidates = [
        repo_root / ".env.openai",
        repo_root / ".env",
        repo_root / ".env.local",
        repo_root / ".env.openai.local",
        repo_root / ".env.openai.dev",
    ]
    candidates.extend(repo_candidates)
    return candidates


def _openai_api_key() -> str | None:
    for key in ("OPENAI_API_KEY", "RESILIENCEOS_OPENAI_API_KEY", "RESILIENCE_OS_OPENAI_API_KEY"):
        value = os.getenv(key, "")
        if value:
            return value

    for env_file in _candidate_env_files():
        env_values = _read_env_file(env_file)
        for key in ("OPENAI_API_KEY", "RESILIENCEOS_OPENAI_API_KEY", "RESILIENCE_OS_OPENAI_API_KEY"):
            value = env_values.get(key, "").strip()
            if value:
                return value

    return None


def _safe_float_env(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int_env(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _openai_config() -> Dict[str, Any]:
    return {
        "base_url": os.getenv("RESILIENCEOS_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("RESILIENCEOS_OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": _safe_float_env(os.getenv("RESILIENCEOS_OPENAI_TEMPERATURE"), 0.2),
        "max_tokens": _safe_int_env(os.getenv("RESILIENCEOS_OPENAI_MAX_TOKENS"), 220),
        "timeout": _safe_float_env(os.getenv("RESILIENCEOS_OPENAI_TIMEOUT_SECONDS"), 20),
    }


def _llm_disabled() -> bool:
    value = os.getenv("RESILIENCEOS_DISABLE_OPENAI_EXPLAIN", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _llm_disabled_for(feature: str) -> bool:
    override = os.getenv(f"RESILIENCEOS_DISABLE_OPENAI_{feature.upper()}", "0").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    return _llm_disabled()


def _safe01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _safe_int(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def _extract_json_block(text: str) -> str | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\\s*([\\s\\S]*?)```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return None


def _extract_plan_snippet(plan: Dict[str, Any]) -> Dict[str, Any]:
    snippet = {
        "evidence_references": plan.get("evidence_references", []),
        "assumptions": plan.get("assumptions", []),
        "missing_data": plan.get("missing_data", []),
        "actionability": {
            "estimated_minutes_to_act": plan.get("actionability", {}).get("estimated_minutes_to_act"),
            "recommended_owner": plan.get("actionability", {}).get("recommended_owner"),
        },
    }

    if "risk_score" in plan:
        snippet["risk_score"] = plan.get("risk_score")
    if "assessed_risk" in plan:
        snippet["assessed_risk"] = plan.get("assessed_risk")
    if "readiness_scores" in plan:
        snippet["readiness_scores"] = plan.get("readiness_scores")
    if "readiness_gap" in plan:
        snippet["readiness_gap"] = plan.get("readiness_gap")

    if "immediate_actions" in plan:
        snippet["immediate_actions"] = plan.get("immediate_actions", [])[:6]
    if "watchlist" in plan:
        snippet["watchlist"] = plan.get("watchlist", [])[:3]

    if "time_horizon_plan" in plan and isinstance(plan.get("time_horizon_plan"), dict):
        snippet["time_horizon_plan"] = {
            horizon: actions[:2]
            for horizon, actions in plan["time_horizon_plan"].items()
            if isinstance(actions, list)
        }

    if "council_review" in plan:
        snippet["council_review"] = plan.get("council_review")
    return snippet


def _openai_trace_enabled() -> bool:
    value = os.getenv("RESILIENCEOS_OPENAI_TRACE", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _trace_openai(feature: str, message: str) -> None:
    if _openai_trace_enabled():
        print(f"[resilienceos-openai:{feature}] {message}", file=sys.stderr)


def _call_openai_for_json(prompt: str, max_tokens: int | None = None) -> tuple[Dict[str, Any] | None, str]:
    api_key = _openai_api_key()
    if not api_key:
        _trace_openai("json", "no api key")
        return None, "no-api-key"

    config = _openai_config()
    base = config["base_url"].rstrip("/")
    endpoint = f"{base}/chat/completions"
    _trace_openai("json", f"POST {endpoint} model={config['model']}")
    request_body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You are a deterministic municipal resilience operations assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens or config["max_tokens"],
        "response_format": {"type": "json_object"},
    }

    requested_tokens = max_tokens or config["max_tokens"]
    for attempt in range(2):
        request_body["max_tokens"] = requested_tokens

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
                raw = response.read().decode("utf-8")
                _trace_openai("json", f"status={getattr(response, 'status', 'n/a')} bytes={len(raw)}")
                response_data = json.loads(raw)
                request_id = response.headers.get("x-request-id") if hasattr(response, "headers") else None
                if request_id:
                    _trace_openai("json", f"request_id={request_id}")
                usage = response_data.get("usage") if isinstance(response_data, dict) else None
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens", "n/a")
                    completion_tokens = usage.get("completion_tokens", "n/a")
                    total_tokens = usage.get("total_tokens", "n/a")
                    _trace_openai(
                        "json",
                        f"usage prompt={prompt_tokens} completion={completion_tokens} total={total_tokens}",
                    )
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as error:
            _trace_openai("json", f"error={error!r}")
            return None, f"error:{error!r}"

        choices = response_data.get("choices") if isinstance(response_data, dict) else None
        if not isinstance(choices, list) or not choices:
            return None, "error:invalid-response"

        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        finish_reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
        if not isinstance(content, str) or not content.strip():
            _trace_openai("json", "empty content from model")
            return None, "error:empty-content"

        payload = _extract_json_block(content.strip())
        if not payload:
            if attempt == 0 and finish_reason == "length":
                requested_tokens = max(requested_tokens * 2, 512)
                _trace_openai("json", "json parse retry: empty extract due length limit")
                continue
            return None, "error:non-json-content"

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as error:
            _trace_openai("json", f"invalid-json: {error}")
            if attempt == 0 and finish_reason == "length":
                requested_tokens = max(requested_tokens * 2, 512)
                _trace_openai("json", "json parse retry: retry with longer max_tokens")
                continue
            return None, f"error:invalid-json:{error}"

        if not isinstance(parsed, dict):
            if attempt == 0 and finish_reason == "length":
                requested_tokens = max(requested_tokens * 2, 512)
                continue
            return None, "error:not-object"

        return parsed, str(config["model"])

    return None, "error:retry-exhausted"


def _build_openai_prompt(plan: Dict[str, Any], audience: str) -> str:
    snippet = _extract_plan_snippet(plan)
    return (
        "You are a municipal emergency operations analyst."
        " Explain the following resilience payload for this audience in one short paragraph plus up to"
        f" 3 concise bullets, with explicit priority logic and urgency reasoning.\n\n"
        f"Audience: {audience}\n"
        f"Payload (JSON):\n{json.dumps(snippet, indent=2, ensure_ascii=False)}\n\n"
        "Constraints:\n"
        "- Keep each bullet short and evidence-based.\n"
        "- Mention why action urgency changes by priority/ETA when visible.\n"
        "- Include the strongest tradeoff across urgency, feasibility, and care for vulnerable households.\n"
    )


def _call_openai_for_explain(payload: Dict[str, Any], audience: str) -> tuple[str | None, str]:
    api_key = _openai_api_key()
    if not api_key:
        return None, "no-api-key"

    config = _openai_config()
    base = config["base_url"].rstrip("/")
    endpoint = f"{base}/chat/completions"
    request_body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You summarize emergency priorities for neighborhood resilience teams."},
            {"role": "user", "content": _build_openai_prompt(payload, audience)},
        ],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as error:
        return None, f"error:{error!r}"

    choices = response_data.get("choices") if isinstance(response_data, dict) else None
    if not isinstance(choices, list) or not choices:
        return None, "error:invalid-response"

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        return None, "error:empty-content"

    return content.strip(), str(config["model"])


def assess(payload: AssessInput) -> AssessOutput:
    risk_score, triggers, readiness, confidence, assumptions, missing = compute_risk_and_readiness(payload)

    llm_assumptions: List[str] = []
    llm_missing: List[str] = []
    if not _llm_disabled_for("ASSESS") and isinstance(_openai_api_key(), str):
        baseline = {
            "risk_score": risk_score,
            "readiness_scores": {
                "warning": readiness.warning,
                "logistics": readiness.logistics,
                "vulnerable_care": readiness.vulnerable_care,
                "comms": readiness.comms,
                "drills": readiness.drills,
            },
            "triggers": [trigger.dict() for trigger in triggers],
            "assumptions": assumptions,
            "missing_data": missing,
            "confidence": confidence,
            "scenario": payload.neighborhood_profile.name,
            "forecast": {
                "rainfall_mm": payload.forecast_summary.rainfall_mm,
                "tide_level_m": payload.forecast_summary.tide_level_m,
                "river_level_m": payload.forecast_summary.river_level_m,
                "alerts": payload.forecast_summary.alerts,
                "complaint_count": payload.forecast_summary.complaint_count,
            },
        }
        baseline_json = json.dumps(baseline, ensure_ascii=False)
        llm_prompt = (
            "Return strict JSON only. You are improving a flood-risk payload.\n"
            "Return compact JSON with only the requested keys.\n"
            "Output JSON with optional keys:\n"
            "- risk_score (int 0-100)\n"
            "- readiness_scores ({warning,logistics,vulnerable_care,comms,drills} int 0-100)\n"
            "- confidence (float 0-1)\n"
            "- extra_hazard_triggers (array up to 2 of {name,score,reason})\n"
            "- assumptions (array of strings)\n"
            "- missing_data (array of strings)\n\n"
            "Keep recommendations conservative and numeric bounds only.\n\n"
            f"Baseline payload JSON:\n{baseline_json}\n"
        )

        llm_payload, llm_model = _call_openai_for_json(llm_prompt, max_tokens=260)
        if llm_payload:
            llm_assumptions.append(f"LLM assess refinement applied by {llm_model}.")
            if "risk_score" in llm_payload:
                risk_score = _safe_int(
                    float(llm_payload.get("risk_score")),
                    0,
                    100,
                )
            if "confidence" in llm_payload:
                confidence = _safe01(float(llm_payload.get("confidence")))
            updated_readiness = llm_payload.get("readiness_scores")
            if isinstance(updated_readiness, dict):
                readiness = readiness.model_copy(
                    update={
                        "warning": _safe_int(float(updated_readiness.get("warning", readiness.warning)), 0, 100),
                        "logistics": _safe_int(float(updated_readiness.get("logistics", readiness.logistics)), 0, 100),
                        "vulnerable_care": _safe_int(float(updated_readiness.get("vulnerable_care", readiness.vulnerable_care)), 0, 100),
                        "comms": _safe_int(float(updated_readiness.get("comms", readiness.comms)), 0, 100),
                        "drills": _safe_int(float(updated_readiness.get("drills", readiness.drills)), 0, 100),
                    }
                )
            if isinstance(llm_payload.get("extra_hazard_triggers"), list):
                for item in llm_payload["extra_hazard_triggers"]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    reason = str(item.get("reason", "")).strip()
                    if not name or not reason:
                        continue
                    score = item.get("score", 0.0)
                    try:
                        score_value = _safe01(float(score))
                    except (TypeError, ValueError):
                        continue
                    triggers.append(HazardTrigger(name=name, score=score_value, reason=reason))
                if triggers:
                    triggers = sorted(triggers, key=lambda trigger: trigger.score, reverse=True)[:5]
            if isinstance(llm_payload.get("assumptions"), list):
                for item in llm_payload["assumptions"]:
                    if isinstance(item, str):
                        llm_assumptions.append(item)
            if isinstance(llm_payload.get("missing_data"), list):
                for item in llm_payload["missing_data"]:
                    if isinstance(item, str):
                        llm_missing.append(item)
        else:
            llm_assumptions.append(f"LLM assess refinement failed ({llm_model}); using deterministic baseline.")
            llm_missing.append(f"LLM assess unavailable: {llm_model}")

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

    assumptions.extend(llm_assumptions)
    missing.extend(llm_missing)
    if _llm_disabled_for("ASSESS"):
        assumptions.append("OPENAI assess path disabled; deterministic baseline used.")

    return AssessOutput(
        risk_score=risk_score,
        top_hazard_triggers=triggers[:5],
        readiness_scores=readiness,
        readiness_gap=", ".join(readiness_gap) if readiness_gap else None,
        assumptions=assumptions,
        confidence=confidence,
        council_review=council,
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

    llm_assumptions: List[str] = []
    llm_missing: List[str] = []
    assessed_risk = payload.assessed_risk
    actionability_minutes = 20
    if not _llm_disabled_for("PLAN") and isinstance(_openai_api_key(), str):
        baseline = {
            "assessed_risk": assessed_risk,
            "time_horizon_plan": {
                horizon: [action.model_dump() for action in actions]
                for horizon, actions in actions_by_horizon.items()
            },
            "resource_inventory": payload.resources.dict(),
            "location": payload.location,
            "scenario": payload.target_zones,
        }
        llm_prompt = (
            "Return strict JSON only for plan refinement.\n"
            "Return compact JSON with only the requested keys.\n"
            "Output JSON with optional keys:\n"
            "- assessed_risk (int 0-100)\n"
            "- action_overrides (array of objects: index, priority?, horizon?, eta_minutes?)\n"
            "- actionability_minutes (int)\n"
            "- assumptions (array strings)\n"
            "- missing_data (array strings)\n"
            "Indexes refer to flattened action order in the baseline list: 24h actions, then 6h, then 1h.\n\n"
            f"Baseline payload JSON:\n{json.dumps(baseline, ensure_ascii=False)}\n"
        )
        llm_payload, llm_model = _call_openai_for_json(llm_prompt, max_tokens=320)
        if llm_payload:
            llm_assumptions.append(f"LLM plan refinement applied by {llm_model}.")
            if "assessed_risk" in llm_payload:
                assessed_risk = _safe_int(
                    float(llm_payload.get("assessed_risk")),
                    0,
                    100,
                )
                council = build_council_review(
                    command_name="plan",
                    assessed_risk=assessed_risk,
                    readiness_scores=None,
                    recommendations=scores,
                )

            if "actionability_minutes" in llm_payload:
                actionability_minutes = _safe_int(float(llm_payload.get("actionability_minutes")), 1, 240)

            overrides = llm_payload.get("action_overrides")
            if isinstance(overrides, list):
                for override in overrides:
                    if not isinstance(override, dict):
                        continue
                    idx = override.get("index")
                    if not isinstance(idx, int):
                        try:
                            idx = int(str(idx))
                        except (TypeError, ValueError):
                            continue
                    if idx < 0 or idx >= len(flat_actions):
                        continue

                    updated = {}
                    if "priority" in override:
                        try:
                            updated["priority"] = _safe_int(float(override.get("priority")), 1, 5)
                        except (TypeError, ValueError):
                            pass
                    if "eta_minutes" in override:
                        try:
                            updated["eta_minutes"] = _safe_int(float(override.get("eta_minutes")), 0, 240)
                        except (TypeError, ValueError):
                            pass
                    if "targets_vulnerable" in override:
                        updated["targets_vulnerable"] = bool(override.get("targets_vulnerable"))
                    if updated:
                        flat_actions[idx] = flat_actions[idx].model_copy(update=updated)

            if isinstance(llm_payload.get("assumptions"), list):
                for item in llm_payload["assumptions"]:
                    if isinstance(item, str):
                        llm_assumptions.append(item)
            if isinstance(llm_payload.get("missing_data"), list):
                for item in llm_payload["missing_data"]:
                    if isinstance(item, str):
                        llm_missing.append(item)
        else:
            llm_assumptions.append(f"LLM plan refinement failed ({llm_model}); using deterministic baseline.")
            llm_missing.append(f"LLM plan unavailable: {llm_model}")

    updated_time_horizon = {"24h": [], "6h": [], "1h": []}
    for action in flat_actions:
        if action.horizon in updated_time_horizon:
            updated_time_horizon[action.horizon].append(action)
    for horizon, actions in updated_time_horizon.items():
        updated_time_horizon[horizon] = sorted(actions, key=lambda action: (action.priority, action.eta_minutes))

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

    matrix = _build_matrix([item for _horizon, items in updated_time_horizon.items() for item in items])

    assumptions: List[str] = []
    missing: List[str] = []
    if resource_count < 5:
        missing.append("resource inventory completeness")
        assumptions.append("Inventory is thin; fallback operational assets are assumed and logged.)")
    assumptions.extend(llm_assumptions)
    missing.extend(llm_missing)
    if _llm_disabled_for("PLAN"):
        assumptions.append("OPENAI plan path disabled; deterministic baseline used.")

    confidence = 0.86 if resource_count >= 5 else 0.7

    return PlanOutput(
        assessed_risk=assessed_risk,
        time_horizon_plan=updated_time_horizon,
        task_assignment_matrix=matrix,
        fallback_routes=fallback_routes,
        shelter_suggestions=shelter_suggestions,
        materials_checklist=materials_checklist,
        council_review=council,
        confidence=min(1.0, max(0.1, confidence + 0.02 if llm_assumptions else 0.0)),
        evidence_references=_merge_evidence(
            payload.location,
            payload.assessed_risk,
            payload.resources,
        ),
        actionability=_build_actionability(
            minutes=actionability_minutes,
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

    fallback = [
        "Priorities are ordered as 24h, 6h, and 1h checkpoints to support pre-impact sequencing.",
        "Actions were generated by deterministic rules from risk, readiness, and resource assumptions.",
    ]
    if "risk_score" in plan:
        fallback.append(f"Risk score {plan.get('risk_score')} shifts the urgency tiering in the selected plan.")
    if "council_review" in plan:
        fallback.append("Council review score is included so leads can compare planner, operations, and safety perspectives.")

    rationale = fallback
    if not _llm_disabled() and isinstance(plan, dict):
        if _openai_api_key():
            generated, model = _call_openai_for_explain(payload.generated_plan, payload.audience)
            if generated:
                rationale = [generated]
                assumptions.append(f"LLM rationale generated by {model}.")
            else:
                assumptions.append("OpenAI explain request failed; using deterministic fallback.")
                missing.append(f"LLM explain unavailable: {model}")
        else:
            assumptions.append("OpenAI API key missing; using deterministic fallback explanation.")

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
