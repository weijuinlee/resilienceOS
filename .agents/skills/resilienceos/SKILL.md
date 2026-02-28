---
name: resilienceos
description: Use when working on the resilienceOS Codex skill/plugin: package install validation, command-level smoke checks, and output behavior checks. Trigger on requests to verify `resilienceos` CLI flows, run baseline command checks, or debug install/discovery issues for this repository.
---

# resilienceOS Skill

## Scope
Use this skill when the task is about:
- installing or validating this repository as a local Codex skill
- running the resilienceOS CLI smoke commands
- checking JSON-vs-markdown output behavior

## Required Inputs
- Repository root at `<repo_root>`
- Working Python environment with access to project dependencies

## Standard Commands
Run these in order unless user changes scope.

1. `python3 -m pip install -e .`
2. `resilienceos assess --scenario singapore --format json`
3. `resilienceos plan --scenario singapore --assessed-risk 90 --format json`
4. `resilienceos assess --format xml`
   - expect a clean CLI failure for invalid format
5. `resilienceos assess --input fixtures/scenario_singapore_coastal.json --format json`

## Verification Notes
- JSON must be the default mode.
- `--format markdown` is opt-in only.
- If install fails, capture the exact `pip`/environment error (permissions, missing deps, network, Python version).
