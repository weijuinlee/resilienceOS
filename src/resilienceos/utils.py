from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT_DIR / "fixtures"

SCENARIOS = {
    "singapore": "scenario_singapore_coastal.json",
    "bali": "scenario_bali_like.json",
    "riverfront": "scenario_riverfront.json",
}


class PluginInputError(ValueError):
    pass


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_command_payload(raw: dict, command: str) -> dict:
    wrappers = {
        "assess": ["assess_input", "assess"],
        "plan": ["plan_input", "plan"],
        "drill": ["drill_input", "drill"],
        "inbox": ["inbox_input", "inbox"],
        "simulate": ["simulate_input", "simulate"],
        "explain": ["explain_input", "explain"],
    }

    for key in wrappers.get(command, []):
        if isinstance(raw.get(key), dict):
            return raw[key]
    return raw


def load_input(input_file: str | None, scenario: str, command: str) -> dict:
    if input_file:
        path = Path(input_file)
        if not path.exists():
            raise PluginInputError(f"Input file not found: {path}")
        raw = load_json(path)
    else:
        if scenario not in SCENARIOS:
            raise PluginInputError(f"Unknown scenario '{scenario}'. Available: {list(SCENARIOS)}")
        path = FIXTURE_DIR / SCENARIOS[scenario]
        raw = load_json(path)

    payload = _extract_command_payload(raw, command)
    if not isinstance(payload, dict):
        raise PluginInputError(f"Invalid payload shape for command '{command}'.")
    return payload


def write_output(path: str | None, payload_obj):
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload_obj.model_dump_json(indent=2), encoding="utf-8")

