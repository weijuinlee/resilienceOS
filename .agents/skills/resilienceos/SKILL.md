---
name: resilienceos
description: Use when configuring, validating, or troubleshooting the resilienceOS Codex skill/plugin. Trigger for install/CLI smoke checks, command behavior validation, and Codex discovery/skill-linking for this repository.
---

# resilienceOS Skill

## Scope
Use this skill when the task is about:
- running or troubleshooting resilienceOS plugin/CLI behavior
- installing and validating this repository as a local Codex skill
- validating command outputs and failure cases
- checking Codex discovery links and skill path registration

## Invocation Triggers
- User asks to run or explain the resilienceOS smoke checks.
- User reports install/discovery failures for the local skill link.
- User asks for JSON/markdown format validation or invalid format error checks.

## Standard Sequence
1. Enter the repository root.
2. Use writable Python environment with dependencies available.
3. For installs, use:
   - `make install-offline`  
   or  
   - `python3 -m pip install -e . --no-build-isolation --no-deps || python3 setup.py develop`
4. Validate these outputs:
   - `resilienceos assess --scenario singapore --format json`
   - `resilienceos plan --scenario singapore --assessed-risk 90 --format json`
   - `resilienceos agent --scenario singapore --include-inbox --include-simulate --format json`
   - `resilienceos assess --input fixtures/scenario_singapore_coastal.json --format json`
5. Validate strict bad-input behavior:
   - `resilienceos assess --format xml` should fail with a validation error.
6. Ensure skill discovery:
   - `make codex-link`
   - validate `~/.codex/skills/resilienceOS` points to the repo.

## Output Expectations
- Primary output is JSON by default.
- Markdown output is only via `--format markdown`.
- `--format xml` must fail cleanly with `Invalid value: format must be json or markdown`.

## Verification Notes
- Confirm exit codes and include command output snippets on failures.
- Treat cleanup/reinstall as needed if stale editable installs cause cache/metadata issues.

## Optional Deterministic Helper
- Use `scripts/resilienceos-smoke-checks.sh` to run the same smoke checks as a single command.

## Additional References
- `references/openai_yaml.md` (metadata field definitions for UI/manifest behavior).
