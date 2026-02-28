from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import engine
from .markdown_render import render
from .models import AssessInput, DrillInput, ExplainInput, InboxInput, PlanInput, SimulateInput
from .utils import PluginInputError, load_input

app = typer.Typer(help="AI resilience agent for neighborhood environmental crisis preparedness")


def _print(payload, command: str, output: Path | None, fmt: str):
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload.model_dump_json(indent=2), encoding="utf-8")

    if fmt == "markdown":
        typer.echo(render(payload, command))
    else:
        typer.echo(payload.model_dump_json(indent=2))


@app.command()
def assess(
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON input payload."),
    scenario: str = typer.Option("singapore", "--scenario", help="Built-in scenario key."),
    output: Optional[Path] = typer.Option(None, "--output", help="Save output JSON to this file."),
    format: str = typer.Option("json", "--format", help="json|markdown"),
):
    """Assess neighborhood flood risk and readiness."""
    if format not in {"json", "markdown"}:
        raise typer.BadParameter("format must be json or markdown")

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
    format: str = typer.Option("json", "--format", help="json|markdown"),
):
    """Generate neighborhood action plan."""
    if format not in {"json", "markdown"}:
        raise typer.BadParameter("format must be json or markdown")

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
    format: str = typer.Option("json", "--format", help="json|markdown"),
):
    if format not in {"json", "markdown"}:
        raise typer.BadParameter("format must be json or markdown")

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
    format: str = typer.Option("json", "--format", help="json|markdown"),
):
    if format not in {"json", "markdown"}:
        raise typer.BadParameter("format must be json or markdown")

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
    format: str = typer.Option("json", "--format", help="json|markdown"),
):
    if format not in {"json", "markdown"}:
        raise typer.BadParameter("format must be json or markdown")

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
    format: str = typer.Option("json", "--format", help="json|markdown"),
):
    if format not in {"json", "markdown"}:
        raise typer.BadParameter("format must be json or markdown")

    try:
        payload = load_input(str(input_file) if input_file else None, scenario, "simulate")
        model = SimulateInput.model_validate(payload)
        result = engine.simulate(model)
    except PluginInputError as error:
        raise typer.BadParameter(str(error))

    _print(result, "simulate", output, format)


if __name__ == "__main__":
    app()

