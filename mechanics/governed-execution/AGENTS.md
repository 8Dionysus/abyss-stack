# AGENTS.md

Applies to `mechanics/governed-execution/`.

This package owns the route shape for governed local-worker execution,
autonomy-gate reporting, return policy, candidate export, and reviewable run
records.

Read the package README, parts, and owner contract only when the touched task
needs their semantic meaning; the package-owned
`mechanics/governed-execution/parts/governed-runner/tests` route is selected on
demand.

Do not turn advisory execution into autonomous authority. Do not bypass gates,
review records, or owner handoffs.

Use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks.
