---
name: resilienceos
description: Use when configuring, validating, or troubleshooting the resilienceOS Codex skill/plugin. Includes install/build, CLI checks, invalid-input validation, and Codex discovery.
---

# resilienceOS Skill

## Scope
Use this skill when the task is about:
- running or troubleshooting resilienceOS plugin/CLI behavior
- installing and validating this repository as a local Codex skill
- validating command outputs and failure cases
- checking Codex discovery links and skill path registration
- preparing judge/demo workflows

## Invocation Triggers
- User asks to run resilienceOS install or health checks.
- User asks to explain, run, or fix smoke check failures.
- User asks for JSON/markdown format behavior and invalid input checks.
- User reports codex discovery/link issues.
- User asks for one-click demo or screenshot workflows.

## Standard Sequence
1. Enter the repository root.
2. Run the health script:
   - `make skill-health` (recommended default)
   - or `bash .agents/skills/resilienceos/scripts/resilienceos-healthcheck.sh`
3. If CLI is missing, install with writable env:
   - `make install-offline`  
   or  
   - `python3 -m pip install -e . --no-build-isolation --no-deps || python3 setup.py develop`
4. Review the healthcheck report and rerun deterministic checks only when needed:
   - `make smoke-skill` for strict command-path output checks
   - `make smoke-fast` for judge-ready compact output
5. Validate outputs manually for confidence:
   - `resilienceos assess --scenario singapore --format json`
   - `resilienceos plan --scenario singapore --assessed-risk 90 --format json`
   - `resilienceos agent --scenario singapore --include-inbox --include-simulate --format json`
   - `resilienceos assess --input fixtures/scenario_singapore_coastal.json --format json`
6. Validate strict bad-input behavior:
   - `resilienceos assess --format xml` should fail with a validation error.
7. Ensure discovery registration:
   - `make codex-link`
   - validate `~/.codex/skills/resilienceOS` points to the repo.
8. Optional judge flow:
   - `make smoke-fast`
   - `make demo-local`
   - `make demo-local-highrisk`
   - `make demo-shot-highrisk`
9. Optional evidence package:
   - Save the health log path printed by `make skill-health` and share a short snippet in bug reports.

## Output Expectations
- Primary output is JSON by default.
- Markdown output is available via `--format markdown`.
- Concise human-readable judge summary is available via `--format concise_brief`.
- `--format xml` must fail cleanly with `Invalid value: format must ...`.
- Healthcheck writes a timestamped log file under `outputs/`.
- User-supplied credentials rule:
  - This skill does not ship provider keys. Operators should configure their own OpenAI key in local environment before running LLM-assisted explain paths.

## Verification Notes
- Confirm exit codes and include command output snippets on failures.
- Treat cleanup/reinstall as needed if stale editable installs cause cache/metadata issues.
- If a failure reproduces after fresh install, include:
  - exact command
  - shell, venv state
  - healthcheck log path
- Optional LLM power path:
  - Set `OPENAI_API_KEY` (or `RESILIENCEOS_OPENAI_API_KEY`) before running `explain`-facing flows.
  - Use `resilienceos explain --scenario singapore --format concise_brief` to validate LLM output.
  - Set `RESILIENCEOS_DISABLE_OPENAI_EXPLAIN=true` to force deterministic-only responses.

## Failure Triage
- Install fails with permission errors:
  - Prefer `make install-offline` in a fresh venv.
  - Clear stale editable metadata and retry.
- Demo or Streamlit command fails on port:
  - Let auto-port fallback handle it, or set `DEMO_PORT` to a free value.
  - For hard conflicts, free the port first: `lsof -i :8501 | awk 'NR>1 {print $2}' | xargs -r kill`.
- `Input file not found`:
  - Re-run from repo root.
  - Verify exact fixture path: `fixtures/scenario_singapore_coastal.json`.
- `resilienceos` command not found:
  - Use the resolved command from `make install-offline`.
  - If needed, run `PYTHONPATH=src python3 -m resilienceos.cli ...` as fallback.
- `readlink` mismatch:
  - Run `make codex-link` and confirm output includes the absolute repo path.
- Missing `jq` when validating JSON:
  - Install once: `brew install jq` (or equivalent platform package), or use raw JSON fields only.

## Optional Deterministic Helper
- Use `scripts/resilienceos-smoke-checks.sh` to run the same smoke checks as a single command.
- Use `scripts/resilienceos-healthcheck.sh` for environment + discovery validation in one pass.

## Helpful one-shot command bundles
- Health + smoke: `make skill-health`
- CLI smoke only: `bash .agents/skills/resilienceos/scripts/resilienceos-smoke-checks.sh`
- 2-minute judge flow: `make smoke-fast`
- Visual pre-baked flow: `make demo-local-highrisk`
- Fast recovery bundle: `rm -rf .venv && make install-offline && make codex-link && make skill-health`

## Additional References
- `references/openai_yaml.md` (metadata field definitions for UI/manifest behavior).
- `scripts/resilienceos-smoke-checks.sh`
- `scripts/resilienceos-healthcheck.sh`
