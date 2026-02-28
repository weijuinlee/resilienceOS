from __future__ import annotations

from pathlib import Path
import os
import json
import sys
import urllib.error
import urllib.request
import urllib.parse
import time

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from resilienceos.engine import _openai_api_key
from resilienceos.engine import _openai_config
from resilienceos.engine import assess as run_assess
from resilienceos.engine import agent as run_agent
from resilienceos.engine import drill as run_drill
from resilienceos.engine import explain as run_explain
from resilienceos.engine import inbox as run_inbox
from resilienceos.engine import plan as run_plan
from resilienceos.engine import simulate as run_simulate
from resilienceos.models import (
    AssessInput,
    DrillInput,
    ExplainInput,
    InboxInput,
    PlanInput,
    SimulateInput,
)
from resilienceos.utils import PluginInputError, SCENARIOS, load_input


PRESET_DEFINITIONS = {
    "manual": {
        "label": "Manual",
        "command": "assess",
        "scenario": "singapore",
        "input": "",
        "override_risk": "false",
        "assessed_risk": "90",
        "include_inbox": "false",
        "include_simulate": "false",
    },
    "judge": {
        "label": "Judge",
        "command": "agent",
        "scenario": "singapore",
        "input": "",
        "override_risk": "true",
        "assessed_risk": "90",
        "include_inbox": "true",
        "include_simulate": "true",
    },
    "high-risk": {
        "label": "High risk",
        "command": "agent",
        "scenario": "singapore",
        "input": "",
        "override_risk": "true",
        "assessed_risk": "95",
        "include_inbox": "true",
        "include_simulate": "true",
    },
}


def _query_param(name: str, default: str = "") -> str:
    params = st.query_params
    if not params:
        return default

    raw = params.get(name, default)
    if isinstance(raw, list):
        return raw[0] if raw else default
    return raw


def _query_flag(name: str, default: bool = False) -> bool:
    return str(_query_param(name, str(default)).lower()) in {"1", "true", "yes", "on"}


def _query_int(name: str, default: int) -> int:
    try:
        value = int(_query_param(name, str(default)))
    except ValueError:
        return default
    return max(0, min(100, value))


def _serialize(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload


def _read_payload(command: str, input_file: str | None, scenario: str) -> dict:
    return load_input(input_file, scenario, command)


def _collect_council_bullets(payload: dict, limit: int = 3) -> list[str]:
    scores = []

    def collect_from_payload(data: dict, prefix: str | None = None) -> None:
        if not isinstance(data, dict):
            return
        review = data.get("council_review")
        if not isinstance(review, dict):
            return
        perspectives = review.get("perspectives")
        if not isinstance(perspectives, list):
            return
        for item in perspectives:
            if not isinstance(item, dict):
                continue
            rationale = item.get("rationale", "")
            perspective = item.get("perspective", "")
            if not rationale or not perspective:
                continue
            label = perspective
            if prefix:
                label = f"{prefix}: {label}"
            scores.append((item.get("score", 0.0), f"{label} ({item.get('score', 0.0):.2f}) - {rationale}"))

    collect_from_payload(payload)
    for key in ("assess", "plan", "inbox", "simulate", "drill"):
        child = payload.get(key, {})
        if isinstance(child, dict):
            collect_from_payload(child, key)

    scores.sort(key=lambda row: row[0], reverse=True)
    return [text for _score, text in scores[:limit]]


def _check_openai_connection() -> tuple[bool, str]:
    api_key = _openai_api_key()
    if not api_key:
        return False, "No API key configured. Set OPENAI_API_KEY in environment."

    config = _openai_config()
    endpoint = f"{config['base_url'].rstrip('/')}/models"
    base_host = urllib.parse.urlparse(config["base_url"]).hostname or config["base_url"]
    started_at = time.time()
    request = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                return False, f"{base_host} returned HTTP {status} for /models"
            response.read(128)
            elapsed_ms = int((time.time() - started_at) * 1000)
            return True, f"Connected to {base_host}/models via {config['model']} in {elapsed_ms}ms"
    except urllib.error.HTTPError as error:
        return False, f"{base_host} rejected /models: HTTP {error.code} ({error.reason})"
    except urllib.error.URLError as error:
        return False, f"Cannot reach {base_host}: {error.reason}"
    except Exception as error:
        return False, f"Connection error to {base_host}: {error}"


def _openai_feature_enabled(feature: str) -> bool:
    value = os.getenv(f"RESILIENCEOS_DISABLE_OPENAI_{feature}", "0").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return False
    return True


def _explain_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""

    existing = payload.get("plain_language_rationale")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    try:
        explanation = run_explain(ExplainInput(generated_plan=payload))
        return explanation.plain_language_rationale.strip()
    except Exception:
        return ""


def run_selected_command(
    command: str,
    scenario: str,
    input_file: str | None,
    assessed_risk_override: int | None,
    include_inbox: bool,
    include_simulate: bool,
):
    if command == "assess":
        payload = _read_payload("assess", input_file, scenario)
        return run_assess(AssessInput.model_validate(payload))

    if command == "plan":
        payload = _read_payload("plan", input_file, scenario)
        if assessed_risk_override is not None:
            payload["assessed_risk"] = assessed_risk_override
        return run_plan(PlanInput.model_validate(payload))

    if command == "drill":
        payload = _read_payload("drill", input_file, scenario)
        return run_drill(DrillInput.model_validate(payload))

    if command == "inbox":
        payload = _read_payload("inbox", input_file, scenario)
        return run_inbox(InboxInput.model_validate(payload))

    if command == "simulate":
        payload = _read_payload("simulate", input_file, scenario)
        return run_simulate(SimulateInput.model_validate(payload))

    if command == "explain":
        payload = _read_payload("explain", input_file, scenario)
        return run_explain(ExplainInput.model_validate(payload))

    assess_payload = _read_payload("assess", input_file, scenario)
    plan_payload = _read_payload("plan", input_file, scenario)
    if assessed_risk_override is not None:
        plan_payload["assessed_risk"] = assessed_risk_override

    assess_model = AssessInput.model_validate(assess_payload)
    plan_model = PlanInput.model_validate(plan_payload)

    inbox_model = None
    if include_inbox:
        inbox_payload = _read_payload("inbox", input_file, scenario)
        inbox_model = InboxInput.model_validate(inbox_payload)

    simulate_model = None
    if include_simulate:
        simulate_payload = _read_payload("simulate", input_file, scenario)
        simulate_model = SimulateInput.model_validate(simulate_payload)

    return run_agent(assess_model, plan_model, inbox_model, simulate_model)


def _safe_run(
    command: str,
    scenario: str,
    input_file: str | None,
    assessed_risk_override: int | None,
    include_inbox: bool,
    include_simulate: bool,
):
    try:
        return run_selected_command(
            command,
            scenario,
            input_file,
            assessed_risk_override,
            include_inbox,
            include_simulate,
        )
    except PluginInputError as error:
        st.error(f"Invalid input: {error}")
    except Exception as error:
        st.error(f"Execution error: {error}")
    return None


def _preset_for(name: str) -> dict:
    return PRESET_DEFINITIONS.get(name, PRESET_DEFINITIONS["manual"])


def _decision_summary(payload: dict) -> list[tuple[str, str]]:
    summary_items = []

    if "risk_score" in payload:
        summary_items.append(("Primary risk", str(payload["risk_score"])))
    elif "assessed_risk" in payload:
        summary_items.append(("Assessed risk", str(payload["assessed_risk"])))

    if "confidence" in payload:
        summary_items.append(("Confidence", f"{payload['confidence']:.2f}"))

    actionability = payload.get("actionability", {})
    if isinstance(actionability, dict):
        minutes = actionability.get("estimated_minutes_to_act")
        owner = actionability.get("recommended_owner")
        if minutes is not None:
            summary_items.append(("Action ETA", f"{minutes} min"))
        if owner:
            summary_items.append(("Recommended owner", owner))

    readiness_scores = payload.get("readiness_scores")
    if isinstance(readiness_scores, dict):
        readiness_gap = payload.get("readiness_gap")
        if readiness_gap:
            summary_items.append(("Readiness gap", str(readiness_gap)))
        if readiness_scores:
            try:
                weakest = min(readiness_scores.values())
                summary_items.append(("Weakest readiness", f"{weakest}"))
            except (TypeError, ValueError):
                pass

    return summary_items


st.set_page_config(page_title="resilienceOS Dashboard", layout="wide")
st.title("resilienceOS AI Dashboard")
st.caption("Visual command runner for neighborhood resilience scenarios")
if "openai_health" not in st.session_state:
    st.session_state["openai_health"] = _check_openai_connection()

st.sidebar.header("OpenAI connection")
if st.sidebar.button("Re-check OpenAI connection"):
    st.session_state["openai_health"] = _check_openai_connection()

openai_ok, openai_msg = st.session_state["openai_health"]
if openai_ok:
    st.sidebar.success("OpenAI: Connected")
    st.sidebar.caption(openai_msg)
    st.sidebar.caption(
        "Assess: "
        + ("enabled" if _openai_feature_enabled("ASSESS") else "disabled (override)")
        + " · Plan: "
        + ("enabled" if _openai_feature_enabled("PLAN") else "disabled (override)")
    )
else:
    st.sidebar.error("OpenAI: Not connected")
    st.sidebar.caption(openai_msg)

scenario_options = list(SCENARIOS.keys())
command_options = [
    "assess",
    "plan",
    "agent",
    "drill",
    "inbox",
    "simulate",
    "explain",
]

st.sidebar.header("Command")
selected_preset = _query_param("preset", "manual")
if selected_preset not in PRESET_DEFINITIONS:
    selected_preset = "manual"

preset_defaults = _preset_for(selected_preset)
selected_preset = st.sidebar.selectbox(
    "Demo preset",
    options=list(PRESET_DEFINITIONS.keys()),
    index=list(PRESET_DEFINITIONS.keys()).index(selected_preset),
    format_func=lambda key: PRESET_DEFINITIONS[key]["label"],
)
preset_defaults = _preset_for(selected_preset)

default_command = _query_param("command", preset_defaults["command"])
if default_command not in command_options:
    default_command = "assess"

default_scenario = _query_param("scenario", preset_defaults["scenario"])
if default_scenario not in scenario_options:
    default_scenario = scenario_options[0]

command = st.sidebar.selectbox("Module", command_options, index=command_options.index(default_command))
scenario = st.sidebar.selectbox("Scenario", scenario_options, index=scenario_options.index(default_scenario))

default_input = _query_param("input", "")
if not default_input:
    default_input = preset_defaults["input"]
input_file = st.sidebar.text_input(
    "Optional input file",
    placeholder="fixtures/scenario_singapore_coastal.json",
    value=default_input,
)
include_inbox = False
include_simulate = False
assessed_risk_override = None

if command in {"plan", "agent"}:
    use_override = st.sidebar.toggle(
        "Override assessed risk",
        value=_query_param("override_risk", preset_defaults["override_risk"]).lower()
        in {"1", "true", "yes", "on"},
    )
    if use_override:
        assessed_risk_default = _query_int("assessed_risk", int(preset_defaults["assessed_risk"]))
        assessed_risk_override = st.sidebar.slider(
            "assessed-risk",
            0,
            100,
            assessed_risk_default,
            1,
        )

if command == "agent":
    include_inbox = st.sidebar.toggle(
        "Include inbox",
        value=_query_flag("include_inbox", preset_defaults["include_inbox"] == "true"),
    )
    include_simulate = st.sidebar.toggle(
        "Include simulate",
        value=_query_flag("include_simulate", preset_defaults["include_simulate"] == "true"),
    )

show_concise_brief = _query_flag("show_concise_brief", True)
show_raw_json = _query_flag("show_raw_json", True)
show_rationale = _query_flag("show_rationale", True)

run_label = f"Run {command.title()}"
auto_run = _query_flag("autostart", False)

if "resilienceos_auto_ran" not in st.session_state:
    st.session_state["resilienceos_auto_ran"] = False

auto_requested = auto_run and not st.session_state["resilienceos_auto_ran"]
clicked = st.button(run_label, type="primary")
should_run = clicked or auto_requested

if auto_requested:
    st.session_state["resilienceos_auto_ran"] = True

if should_run:
    with st.spinner("Running resilienceOS..."):
        payload_object = _safe_run(
            command,
            scenario,
            input_file.strip() or None,
            assessed_risk_override,
            include_inbox,
            include_simulate,
        )
        if payload_object is None:
            st.stop()

        payload = _serialize(payload_object)
        st.success(f"{command.title()} complete")
        st.markdown("### Decision summary")
        summary_items = _decision_summary(payload)
        if summary_items:
            summary_columns = st.columns(min(4, len(summary_items)) or 1)
            for index, (label, value) in enumerate(summary_items):
                summary_columns[index % len(summary_columns)].metric(label, value)
        else:
            st.info("Decision summary not available for this payload shape.")

        st.subheader("Summary")
        col1, col2, col3 = st.columns(3)

        if "risk_score" in payload:
            col1.metric("Risk Score", payload.get("risk_score"))
        if "compliance_score" in payload:
            col1.metric("Drill Compliance", f"{payload.get('compliance_score')}%")
        if "confidence" in payload:
            col2.metric("Confidence", f"{payload.get('confidence', 0):.2f}")
        if payload.get("actionability", {}).get("estimated_minutes_to_act") is not None:
            col3.metric(
                "Action ETA",
                f"{payload['actionability']['estimated_minutes_to_act']} min",
            )

        if "readiness_scores" in payload:
            st.write("Readiness")
            st.bar_chart(payload["readiness_scores"])

        if "time_horizon_plan" in payload:
            st.write("### Plan by horizon")
            for horizon, actions in payload["time_horizon_plan"].items():
                with st.expander(f"{horizon} horizon"):
                    if actions:
                        st.table(actions)
                    else:
                        st.write("No actions")

        if command == "agent" and payload.get("immediate_actions"):
            st.write("### Immediate actions")
            for item in payload["immediate_actions"]:
                st.write(f"- {item}")

        if show_rationale:
            st.subheader("Why this order?")
            rationale_bullets = _collect_council_bullets(payload, limit=3)
            if rationale_bullets:
                for item in rationale_bullets:
                    st.write(f"- {item}")
            else:
                st.info("No rationale bullets available.")

        if show_concise_brief:
            st.subheader("Concise brief")
            concise_lines = _explain_text(payload)
            if concise_lines:
                st.write(concise_lines)
            else:
                st.info("Concise brief not available for this payload.")

        if show_raw_json:
            with st.expander("Machine-readable JSON output"):
                st.json(payload)

        if "incident_clusters" in payload:
            st.write("### Incident clusters")
            st.json(payload["incident_clusters"])

        if "plain_language_rationale" in payload:
            st.write("### Rationale")
            st.write(payload["plain_language_rationale"])
else:
    st.info("Pick a command and click run to generate outputs.")

st.caption(f"Loaded scenarios: {', '.join(scenario_options)}")
