# Quest District

This directory holds tracked `abyss-stack` obligations that should survive the
current diff.

It is not a private scratchpad and not a second roadmap. Program direction
belongs in [ROADMAP.md](../ROADMAP.md). The compact root quest index is
[QUESTBOOK.md](../QUESTBOOK.md).

## Source Surfaces

- `ABYSS-STACK-Q-*.yaml` are active quest source records.
- `schemas/` defines the local quest and dispatch contracts.
- `examples/` carries public-safe catalog and dispatch examples derived from the
  active quest records.

## Boundary

Quests here track `abyss-stack` runtime, deployment, lifecycle, platform,
diagnostic, and infrastructure follow-through. They do not author sibling
repository doctrine and do not prove runtime state by themselves.

Historical mechanic quest stubs are routed through the owning mechanic legacy
path so this root district stays current.

## Checks

```bash
python scripts/validate_stack.py
python -m pytest tests/test_validate_stack_questbook.py
```
