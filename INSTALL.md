# Install and run resilienceOS

1. Create and activate a Python environment (optional but recommended)
2. Install package in editable mode:

```bash
pip install -e .
```

3. Run with a default fixture:

```bash
resilienceos assess --scenario singapore
resilienceos plan --scenario singapore
resilienceos drill --scenario singapore
resilienceos simulate --scenario singapore
```

Use `--format markdown` for a concise human-readable brief.
