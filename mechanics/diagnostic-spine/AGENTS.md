# AGENTS.md

Applies to `mechanics/diagnostic-spine/`.

This package owns the route shape for doctor readiness, status truth goals,
diagnostic bundle output, last-good anchors, and repair handoff candidates.

Read the package README, parts, and owner contract only when the touched task
needs their semantic meaning; `build_diagnostic_surface_catalog.py --check`
is selected through the on-demand validation route.

Do not make `aoa-doctor` louder than readiness, and do not treat diagnostic
handoff candidates as completed repairs.

Use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks.
