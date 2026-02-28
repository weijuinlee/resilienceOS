# `agents/openai.yaml` reference

This file configures optional Codex App UI metadata and optional invocation policy for this skill.

- `interface.display_name`: Human-facing name.
- `interface.short_description`: Short one-line description shown in skill pickers.
- `interface.default_prompt`: Suggested default context when opening this skill.
- `interface.icon_small`: Relative path to icon for compact UI usage.
- `interface.icon_large`: Relative path to icon for large chips/screens.
- `interface.brand_color`: Hex string (for theme accents).
- `policy.allow_implicit_invocation`: Set to `true` to allow auto-triggering from context.
- `dependencies`: Optional external tools (e.g., MCP servers).

When these values are changed, keep this file aligned with `SKILL.md` and regenerate
`agents/openai.yaml` if your workflow includes script-based generation.

Suggested values for this repository:
- `display_name`: `ResilienceOS`
- `short_description`: `Validate and run resilienceOS AI climate resilience workflows.`
- `default_prompt`: as implemented in `agents/openai.yaml`
