# Install and run resilienceOS

1. Create and activate a writable Python environment (recommended).

```bash
python3 -m venv .venv
source .venv/bin/activate
```

For offline or restricted-network environments, use the following one-shot flow:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -e . --no-build-isolation --no-deps
```

2. Install package in editable mode:

```bash
python3 -m pip install -e . --no-build-isolation --no-deps
```

If your environment has reliable internet, you can omit `--no-build-isolation`:

```bash
python3 -m pip install -e .
```

3. Run the default JSON smoke check:

```bash
resilienceos assess --scenario singapore --format json
resilienceos plan --scenario singapore --assessed-risk 90 --format json
resilienceos agent --scenario singapore --include-inbox --include-simulate --format json
```

JSON-first behavior:
- JSON is default: `--format json`
- Markdown remains opt-in: `--format markdown`

If installation fails or `resilienceos` command is not on PATH, run directly from the
repository:

```bash
PYTHONPATH=src python3 -m resilienceos.cli assess --scenario singapore --format json
PYTHONPATH=src python3 -m resilienceos.cli plan --scenario singapore --assessed-risk 90 --format json
PYTHONPATH=src python3 -m resilienceos.cli assess --format xml
PYTHONPATH=src python3 -m resilienceos.cli agent --scenario singapore --include-inbox --include-simulate --format json
```

If you want fixtures outside the current directory:

```bash
PYTHONPATH=src python3 -m resilienceos.cli assess --input fixtures/scenario_singapore_coastal.json --format json
```

## Make it discoverable as a Codex skill

```bash
mkdir -p ~/.codex/skills
ln -sfn "$(pwd)" ~/.codex/skills/resilienceOS
```

Restart Codex (or the current Codex client/session) and verify that `resilienceOS`
appears in the skill list. This repo exposes:
- `resilienceos.skill.json` for schema/command discovery
- `.agents/skills/resilienceos/SKILL.md` for Codex UI/runtime metadata

## Make targets

Common release/dev checks:

```bash
make install          # create .venv + editable install
make install-offline  # create .venv using system packages and install without extra downloads
make smoke            # run fallback smoke checks from source
make smoke-fail       # validate clean failure on unsupported format
make smoke-input      # fixture-backed smoke check
make codex-link       # register in ~/.codex/skills for discovery
```
