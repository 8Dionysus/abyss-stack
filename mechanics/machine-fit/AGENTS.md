# AGENTS.md

Applies to `mechanics/machine-fit/`.

This package owns the route shape for reference platform facts, host facts,
machine-fit capture, platform adaptation, and read-only machine bridge
integration.

Read only the source and owner contract needed for the current touched surface; entering this subtree does not require an unconditional README or documentation inventory.

Stable operator wrappers such as `scripts/aoa-host-facts`,
`scripts/aoa-machine-bridge`, and `scripts/aoa-machine-fit` stay at the root
command surface; their implementation bodies belong under this package's
part-local backend paths.

Do not mutate /srv/abyss-machine, private host captures, Podman storage, or
accelerator settings from package docs.

Use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks.
