# resilienceOS

resilienceOS is a production-ready **AI resilience agent** for neighborhood flood preparedness.
All commands emit **JSON by default** for automation and orchestrator parsing.
Use `--format markdown` for a rendered summary or `--format concise_brief` for a compact, judge-friendly "what should I do now" summary.

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

## Optional LLM-enhanced resilience logic

Each user/deployment should use their own OpenAI key locally (bring-your-own-key).
Do not commit provider keys in this repository or in preset files.

You can enable three optional enhancement modes with your own OpenAI key:

- `assess` risk-readiness refinement
- `plan` action-priority/ordering refinement
- `explain` richer human-readable rationale

```bash
export OPENAI_API_KEY="sk-..."
export RESILIENCEOS_OPENAI_API_KEY="sk-..."
export RESILIENCEOS_OPENAI_MODEL="gpt-4o-mini"   # optional
export RESILIENCEOS_OPENAI_MAX_TOKENS="260"       # optional
```

Quick local setup:

```bash
cp openai.env.example .env.openai
# put your real key in .env.openai
# Works with either raw key-value lines or `export KEY=...`.
```

When configured, `assess`, `plan`, and `explain` can use LLM-assisted refinement/reasoning while preserving deterministic behavior when unavailable.

Fallback behavior:
- If no key is set, skill stays deterministic.
- If the request fails, it silently falls back to deterministic bullet reasoning and adds an assumption note.

Disable explicitly with:

```bash
export RESILIENCEOS_DISABLE_OPENAI_EXPLAIN="true"
```

## Running

```bash
python3 -m pip install -e . --no-build-isolation --no-deps || python3 setup.py develop
resilienceos assess --scenario singapore --format json
resilienceos agent --scenario singapore --include-inbox --include-simulate --format json
resilienceos plan --scenario singapore --format markdown
resilienceos plan --scenario singapore --format concise_brief
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

### 2-minute hackathon demo

Use this sequence for a short, repeatable demo:

```bash
resilienceos assess --scenario singapore --format json | jq '.risk_score, .readiness_scores'
resilienceos plan --scenario singapore --assessed-risk 90 --format json | jq '.time_horizon_plan["6h"], .task_assignment_matrix[:2]'
resilienceos agent --scenario singapore --include-inbox --include-simulate --format json | jq '.scenario, .immediate_actions, .watchlist'
resilienceos explain --scenario singapore --format json | jq '.plain_language_rationale'
resilienceos plan --scenario singapore --assessed-risk 90 --format concise_brief
resilienceos assess --format xml
```

Or run the exact same flow via Makefile:

```bash
make smoke-fast
```
For a complete validation bundle that includes positive paths plus the expected invalid-format failure, use:

```bash
make smoke-skill
```

## Visual dashboard (Streamlit)

Run a demo-friendly dashboard to call resilienceOS from a browser:

```bash
make ui
```

The dashboard lets you:
- switch between `assess`, `plan`, `agent`, `drill`, `inbox`, `simulate`, and `explain`
- run scenarios from built-in fixtures or a local JSON file
- pass plan/agent risk overrides and optional inbox/simulate modules
- inspect rendered summaries and raw JSON payloads instantly
- the judge preset shows both concise brief rationale and machine JSON together

If `streamlit` is not already in your venv, `make ui` installs it first.

### Judge-ready one-click demo

Use a preloaded demo URL and auto-run to reduce clicks:

```bash
DEMO_COMMAND=agent DEMO_SCENARIO=singapore make demo-ui
```

This opens `resilienceOS` with:
- preselected module/scenario
- optional assessed-risk override
- auto-run enabled

For a repeatable screenshot capture:

```bash
DEMO_COMMAND=agent DEMO_SCENARIO=singapore DEMO_SCREENSHOT=outputs/demo-dashboard.png make demo-shot
```

If Playwright is not installed, the target prints a fallback instruction and the local screenshot workflow.

### Fully pre-baked judge mode

Run the judge preset with no inline variables:

```bash
make demo-local
```

If port 8501 is already busy, the demo script automatically falls back to the next free local port and prints the URL it opens.

If you want an automatic screenshot from the same preset:

```bash
make demo-local-shot
```

Use the high-risk preset when you want stronger urgency and deeper response pressure in the demo:

```bash
make demo-local-highrisk
make demo-shot-highrisk
```

Preset files:
- `scripts/demo-presets/judge.env`
- `scripts/demo-presets/high-risk.env`

Output notes for judges:
- `assess` returns a machine-readable readiness/risk payload.
- `plan` returns a priority action plan by horizon.
- `agent` includes integrated assess/plan/inbox/simulate coordination.
- `explain` returns `plain_language_rationale` (human-readable explanation field).
- invalid `--format xml` fails fast with a clear validation error.

Judge-facing CLI mode:
- `--format concise_brief` gives a short, high-signal text summary
- "Why this order?" bullets are drawn from top council-review rationale scores

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

### Publish/distribution (GitHub + skill-installer)

For marketplace-style sharing:

1. Push this repository to GitHub.
2. In downstream environments, install from repo:

```bash
git clone <https://github.com/<org>/<repo>.git>
cd <repo>
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
make install-offline
make codex-link
```

Or, when `skill-installer` is available in the user environment:

```bash
skill-installer install <https://github.com/<org>/<repo>.git>
```

After install, restart Codex and verify `resilienceOS` appears in the skill list.
Published Smithery entry: https://smithery.ai/skills/wjuin/resilienceos

## Release/build helpers

Use `make` for repeatable checks:

```bash
make install              # creates .venv and installs editable
make smoke                # JSON smoke checks via direct PYTHONPATH fallback
make smoke-fast           # 2-minute judge-friendly demo with expected validation failure
make smoke-skill          # deterministic full skill smoke path using skill helper script
make smoke-installed      # JSON smoke checks via installed CLI (if install succeeds)
make smoke-fail           # expected validation-failure path for invalid format
make codex-link           # register this repo in ~/.codex/skills
```

## Local files
- `src/resilienceos/` command handlers, models, and scoring logic
- `fixtures/` dry-run scenarios and data
- `outputs/` generated example outputs
