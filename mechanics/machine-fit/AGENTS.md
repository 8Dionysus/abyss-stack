# AGENTS.md

Applies to `mechanics/machine-fit/`.

This package owns the route shape for reference platform facts, host facts,
machine-fit capture, platform adaptation, and read-only machine bridge
integration.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Stable operator wrappers such as `scripts/aoa-host-facts`,
`scripts/aoa-machine-bridge`, and `scripts/aoa-machine-fit` stay at the root
command surface; their implementation bodies belong under this package's
part-local backend paths.

Do not mutate /srv/abyss-machine, private host captures, Podman storage, or
accelerator settings from package docs.

Validation:

```bash
python scripts/validate_stack.py
python -m py_compile mechanics/machine-fit/parts/host-facts/aoa_host_facts.py mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py mechanics/machine-fit/parts/platform-adaptations/aoa_platform_adaptation.py
```
