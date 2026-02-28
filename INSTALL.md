# Install and run resilienceOS

1. Create and activate a Python environment (optional but recommended)
2. Install package in editable mode:

```bash
pip install -e .
```

3. Run with a default fixture (JSON is default output):

```bash
resilienceos assess --scenario singapore
resilienceos plan --scenario singapore
resilienceos drill --scenario singapore
resilienceos simulate --scenario singapore
```

Use `--format markdown` for a concise human-readable brief.

JSON-first usage:
- Omit `--format` or use `--format json` for machine-parsing pipelines.
- Use `--format markdown` when you need a human-readable report only.
