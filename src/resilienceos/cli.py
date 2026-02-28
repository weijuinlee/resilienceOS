from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from . import engine
from .markdown_render import render
from .models import (
    AgentOutput,
    AssessInput,
    DrillInput,
    ExplainInput,
    InboxInput,
    PlanInput,
    SimulateInput,
)
from .utils import PluginInputError, load_input

app = typer.Typer(help="AI resilience agent for neighborhood environmental crisis preparedness")

ALLOWED_FORMATS = {"json", "markdown", "concise_brief"}


def _serialize_payload(payload) -> str:
    if hasattr(payload, "model_dump"):
        return payload.model_dump_json(indent=2)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _coerce_payload_dict(payload) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if isinstance(payload, dict):
        return payload
    return {}


def _explain_rationale(payload_dict: dict) -> str:
    if payload_dict.get("plain_language_rationale"):
        return payload_dict["plain_language_rationale"]

    try:
        explain_payload = {"generated_plan": payload_dict}
        explain_model = ExplainInput.model_validate(explain_payload)
        explain_output = engine.explain(explain_model)
        return explain_output.plain_language_rationale
    except Exception:
        return ""


def _collect_top_rationale_bullets(payload_dict: dict, limit: int = 3) -> list[str]:
    collected = []

    def collect_from_payload(source: dict, label: str | None = None) -> None:
        if not isinstance(source, dict):
            return
        review = source.get("council_review")
        if not isinstance(review, dict):
            return
        perspectives = review.get("perspectives")
        if not isinstance(perspectives, list):
            return

        for item in perspectives:
            if not isinstance(item, dict):
                continue
            rationale = item.get("rationale", "")
            if not rationale:
                continue

            perspective = item.get("perspective", "planner")
            score = item.get("score", 0.0)
            if label:
                perspective = f"{label}: {perspective}"
            collected.append((score, f"{perspective}: {rationale}"))

    collect_from_payload(payload_dict, None)
    if not collected and isinstance(payload_dict, dict):
        for nested_key in ("assess", "plan", "inbox", "simulate", "drill"):
            collect_from_payload(payload_dict.get(nested_key, {}), nested_key)

    collected.sort(key=lambda item: item[0], reverse=True)
    return [text for _score, text in collected[:limit]]


def _format_concise_brief(payload, command: str) -> str:
    payload_dict = _coerce_payload_dict(payload)
    lines = [f"resilienceOS concise brief: {command}"]
    lines.append(f"Generated: {payload_dict.get('generated_at', 'unknown')}")

    if "risk_score" in payload_dict:
        lines.append(f"Risk score: {payload_dict['risk_score']}/100")
    if "assessed_risk" in payload_dict:
        lines.append(f"Assessed risk: {payload_dict['assessed_risk']}/100")
    if "confidence" in payload_dict:
        lines.append(f"Confidence: {payload_dict['confidence']:.2f}")

    actionability = payload_dict.get("actionability") or {}
    if isinstance(actionability, dict):
        owner = actionability.get("recommended_owner", "local lead")
        minutes = actionability.get("estimated_minutes_to_act")
        if minutes is not None:
            lines.append(f"Recommended action window: {minutes} minutes (owner: {owner})")

    if "time_horizon_plan" in payload_dict:
        lines.append("Top plan actions:")
        for horizon, actions in payload_dict["time_horizon_plan"].items():
            if not isinstance(actions, list):
                continue
            for action in actions[:2]:
                what = action.get("what") if isinstance(action, dict) else ""
                who = action.get("who") if isinstance(action, dict) else ""
                eta = action.get("eta_minutes") if isinstance(action, dict) else ""
                lines.append(f"- [{horizon}] {what} | owner: {who} | ETA {eta}m")

    if "immediate_actions" in payload_dict and isinstance(payload_dict["immediate_actions"], list):
        lines.append("Immediate actions:")
        for item in payload_dict["immediate_actions"][:4]:
            lines.append(f"- {item}")

    rationale_bullets = _collect_top_rationale_bullets(payload_dict, limit=3)
    lines.append("Why this order?")
    if rationale_bullets:
        for bullet in rationale_bullets:
            lines.append(f"- {bullet}")
    else:
        lines.append("- No council review rationale available.")

    explain_text = _explain_rationale(payload_dict)
    if explain_text:
        lines.append(f"Explain: {explain_text}")

    return "\n".join(lines)


def _print(payload, command: str, output: Path | None, fmt: str):
    if fmt == "concise_brief":
        payload_text = _format_concise_brief(payload, command)
    elif fmt == "markdown":
        payload_text = render(payload, command)
    else:
        payload_text = _serialize_payload(payload)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload_text, encoding="utf-8")
    typer.echo(payload_text)


def _validate_format(fmt: str) -> None:
    if fmt not in ALLOWED_FORMATS:
        raise typer.BadParameter("format must be json, markdown, or concise_brief")


@app.command()
def assess(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON input payload."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON to this file."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    """Assess neighborhood flood risk and readiness."""
    _validate_format(format)

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "assess")
        model = AssessInput.model_validate(payload)
        result = engine.assess(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "assess", output, format)


@app.command()
def plan(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON payload for plan command."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    assessed_risk: Optional[int] = typer.Option(None, "--assessed-risk", min=0, max=100, help="Optional risk override for quick demos."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    """Generate neighborhood action plan."""
    _validate_format(format)

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "plan")
        if assessed_risk is not None:
            payload["assessed_risk"] = assessed_risk
        model = PlanInput.model_validate(payload)
        result = engine.plan(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "plan", output, format)


@app.command()
def drill(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON payload for drill command."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    _validate_format(format)

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "drill")
        model = DrillInput.model_validate(payload)
        result = engine.drill(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "drill", output, format)


@app.command()
def inbox(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON payload for inbox command."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    _validate_format(format)

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "inbox")
        model = InboxInput.model_validate(payload)
        result = engine.inbox(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "inbox", output, format)


@app.command()
def explain(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON payload containing generated_plan field."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    _validate_format(format)

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "explain")
        model = ExplainInput.model_validate(payload)
        result = engine.explain(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "explain", output, format)


@app.command()
def simulate(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON payload for simulation."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    _validate_format(format)

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "simulate")
        model = SimulateInput.model_validate(payload)
        result = engine.simulate(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "simulate", output, format)


@app.command()
def agent(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON payload for agent workflow."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    include_inbox: bool = typer.Option(False, "--include-inbox", help="Include social signal triage in this run."),
    include_simulate: bool = typer.Option(False, "--include-simulate", help="Include simulation impact run in this bundle."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON."),
    format: str = typer.Option("json", "--format", help="json|markdown|concise_brief"),
):
    """Run an adaptive resilience agent pass across assess, plan, and optional monitors."""
    _validate_format(format)

    try:
        assess_payload = load_input(str(input_file) if input_file else None, scenario, "assess")
        plan_payload = load_input(str(input_file) if input_file else None, scenario, "plan")
        assess_model = AssessInput.model_validate(assess_payload)
        plan_model = PlanInput.model_validate(plan_payload)

        inbox_model = None
        if include_inbox:
            inbox_payload = load_input(str(input_file) if input_file else None, scenario, "inbox")
            inbox_model = InboxInput.model_validate(inbox_payload)

        simulate_model = None
        if include_simulate:
            simulate_payload = load_input(str(input_file) if input_file else None, scenario, "simulate")
            simulate_model = SimulateInput.model_validate(simulate_payload)

        result: AgentOutput = engine.agent(
            assess_model,
            plan_model,
            include_inbox=inbox_model,
            include_simulate=simulate_model,
        )
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "agent", output, format)


if __name__ == "__main__":
    app()
