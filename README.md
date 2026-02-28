# resilienceOS

resilienceOS is a production-ready **AI resilience agent** for neighborhood flood preparedness.
All commands emit **JSON by default** for automation and orchestrator parsing.
Use `--format markdown` only when you want a human-readable summary.

It is built for one-person, demo-ready deployments and runs locally first with deterministic outputs.

## Problem
Urban neighborhoods face frequent flood hazards but need to act before impact.
This plugin turns forecast, infrastructure, and community signals into clear readiness scores,
priority tasks, and field-ready plans.

## Architecture

```text
+------------------+      +------------------+
|  Fixtures / APIs  | ---> |  Input Loader     | ---> +----------------+
|  (local JSON)     |      |  (schema validate)|       |  Risk + Readiness|
+------------------+      +------------------+ ---> |  Engine          |
                                              +-------+----------+
                                                      |
                                                      v
                                            +----------------------+
                                            |  Evaluation Module    |
                                            | (urgency/feasibility/ |
                                            | equity/efficiency)    |
                                            +-----------+----------+
                                                        |
                                                        v
                                            +----------------------+
                                            |  Command handlers     |
                                            | assess / plan / ...   |
                                            +-----------+----------+
                                                        |
                                                        v
                                            +----------------------+
                                            |  CLI + Markdown/JSON |
                                            +----------------------+
```

The CLI has seven commands:
- `assess`
- `plan`
- `agent`
- `drill`
- `inbox`
- `explain`
- `simulate`

Each output includes:
- `version`
- `generated_at`
- `confidence`
- `actionability`
- evidence references and assumptions.

## Optional API mode
The current implementation is local-first and deterministic.
Hook points for API sources are in `src/resilienceos/utils.py` (`load_input`) and can be replaced by live fetchers without changing command behavior.

## Running

```bash
python3 -m pip install -e . --no-build-isolation
resilienceos assess --scenario singapore --format json
resilienceos agent --scenario singapore --include-inbox --include-simulate --format json
resilienceos plan --scenario singapore --format markdown
resilienceos drill --scenario singapore
resilienceos inbox --scenario singapore
resilienceos explain --scenario singapore
resilienceos simulate --scenario singapore
```

If installation is blocked by permissions, run from repository checkout without
installing:

```bash
PYTHONPATH=src python3 -m resilienceos.cli assess --scenario singapore --format json
PYTHONPATH=src python3 -m resilienceos.cli assess --scenario singapore --input fixtures/scenario_singapore_coastal.json --format json
PYTHONPATH=src python3 -m resilienceos.cli assess --format xml
```

### Sample one-command demo path

```bash
resilienceos assess --scenario singapore --output outputs/assess_singapore.json
resilienceos plan --scenario singapore --output outputs/plan_singapore.json
resilienceos simulate --scenario singapore --output outputs/simulate_singapore.json
```

A full run typically finishes well under 60 seconds for small fixture payloads.

## Codex Skill plugin registration

To make this discoverable as a Codex skill, install this repository folder under your
Codex skills path and restart Codex:

```bash
mkdir -p ~/.codex/skills
ln -sfn "$(pwd)" ~/.codex/skills/resilienceOS
```

When Codex loads skills from filesystem manifests, it scans:
- `resilienceos.skill.json` at the plugin root
- optional `.agents/...` metadata for UI/runtime display

## Release/build helpers

Use `make` for repeatable checks:

```bash
make install              # creates .venv and installs editable
make smoke                # JSON smoke checks via direct PYTHONPATH fallback
make smoke-installed      # JSON smoke checks via installed CLI (if install succeeds)
make smoke-fail           # expected validation-failure path for invalid format
make codex-link           # register this repo in ~/.codex/skills
```

## Local files
- `src/resilienceos/` command handlers, models, and scoring logic
- `fixtures/` dry-run scenarios and data
- `outputs/` generated example outputs
