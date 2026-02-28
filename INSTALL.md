# Install and run resilienceOS

1. Create and activate a writable Python environment (recommended).

```bash
python3 -m venv .venv
source .venv/bin/activate
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
```

If you want fixtures outside the current directory:

```bash
PYTHONPATH=src python3 -m resilienceos.cli assess --input fixtures/scenario_singapore_coastal.json --format json
```
