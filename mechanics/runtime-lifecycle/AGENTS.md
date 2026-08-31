# AGENTS.md

Applies to `mechanics/runtime-lifecycle/`.

This package owns the route shape for install, layout, start, stop, wait,
smoke, logs, systemd user units, and operator runbook flow.
Current lifecycle docs include `docs/install/DEPLOYMENT.md`, `docs/install/FIRST_RUN.md`, and
`docs/operations/RUNBOOK.md`.

Read only the source and owner contract needed for the current touched surface; entering this subtree does not require an unconditional README or documentation inventory.

Do not start services, enable units, widen host exposure, or mutate live state
from this package. Runtime activation remains an explicit operator action.

Validation:

Validation is on-demand: use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
