# AGENTS.md

Applies to `mechanics/machine-fit/`.

This package owns the route shape for reference platform facts, host facts,
machine-fit capture, platform adaptation, and future read-only machine bridge
integration.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`, and
`PARTS.md` before editing.

Do not mutate /srv/abyss-machine, private host captures, Podman storage, or
accelerator settings from package docs.

Validation:

```bash
python scripts/validate_stack.py
bash -n scripts/aoa-host-facts scripts/aoa-machine-fit scripts/aoa-platform-adaptation
```
