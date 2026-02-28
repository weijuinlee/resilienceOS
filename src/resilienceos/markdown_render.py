from __future__ import annotations

import json
from typing import Any

from jinja2 import Template


def _to_dict(payload: Any) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload


TEMPLATES = {
    "assess": Template(
        """# Assess

Timestamp: {{ payload.generated_at }}
Risk score: {{ payload.risk_score }} / 100
Confidence: {{ payload.confidence }}
Actionability: ETA {{ payload.actionability.estimated_minutes_to_act }}m, owner {{ payload.actionability.recommended_owner }}

## Top hazards
{% for item in payload.top_hazard_triggers %}
- {{ loop.index }}. {{ item.name }} ({{ "%.2f"|format(item.score*100) }}): {{ item.reason }}
{% endfor %}

## Readiness
- warning: {{ payload.readiness_scores.warning }}
- logistics: {{ payload.readiness_scores.logistics }}
- vulnerable care: {{ payload.readiness_scores.vulnerable_care }}
- comms: {{ payload.readiness_scores.comms }}
- drills: {{ payload.readiness_scores.drills }}

Council rank: {{ payload.council_review.final_rank }}
"""
    ),
    "plan": Template(
        """# Plan

Assessed risk: {{ payload.assessed_risk }}
Confidence: {{ payload.confidence }}

## 24h / 6h / 1h
{% for horizon, items in payload.time_horizon_plan.items() %}
### {{ horizon }}
{% for action in items %}
- [P{{ action.priority }}] {{ action.what }} | owner={{ action.who }} | eta={{ action.eta_minutes }}m
{% endfor %}
{% endfor %}

Fallback routes: {{ payload.fallback_routes | join(", ") }}
Shelters: {{ payload.shelter_suggestions | join(", ") }}
Materials: {{ payload.materials_checklist | join(", ") }}
Council rank: {{ payload.council_review.final_rank }}
"""
    ),
    "drill": Template(
        """# Drill

Compliance score: {{ payload.compliance_score }}
Confidence: {{ payload.confidence }}

Missed steps:
{% for step in payload.missed_steps %}
- {{ step }}
{% endfor %}

Corrective actions:
{% for step in payload.corrected_procedures %}
- {{ step }}
{% endfor %}

Council rank: {{ payload.council_review.final_rank }}
"""
    ),
    "inbox": Template(
        """# Inbox

Confidence: {{ payload.confidence }}

## Clusters
{% for key, value in payload.incident_clusters.items() %}
- {{ key }}: {{ value }}
{% endfor %}

## Escalations
{% for item in payload.escalation_decisions %}
- {{ item.incident_id }} -> {{ item.decision }}
{% endfor %}
"""
    ),
    "explain": Template(
        """# Explain

{{ payload.plain_language_rationale }}

Assumptions:
{% for item in payload.assumptions %}
- {{ item }}
{% endfor %}

Missing data:
{% for item in payload.missing_data %}
- {{ item }}
{% endfor %}
"""
    ),
    "simulate": Template(
        """# Simulate

Predicted impact:
{% for segment in payload.predicted_impact_by_segment %}
- {{ segment.segment }}: {{ segment.estimated_people_impacted }} affected, confidence {{ segment.confidence }}
{% endfor %}

First 60 minutes:
{% for action in payload.first_60_minute_actions %}
- {{ action.what }} ({{ action.who }}) ETA {{ action.eta_minutes }}m
{% endfor %}

Council rank: {{ payload.council_review.final_rank }}
"""
    ),
}


def render(payload: Any, command: str) -> str:
    payload_data = _to_dict(payload)
    tpl = TEMPLATES.get(command)
    if tpl is None:
        return json.dumps(payload_data, indent=2)
    return tpl.render(payload=payload_data)

