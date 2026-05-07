# AGENTS.md

Applies to `mechanics/diagnostic-spine/`.

This package owns the route shape for doctor readiness, status truth goals,
diagnostic bundle output, last-good anchors, and repair handoff candidates.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`, and
`PARTS.md` before editing.

Do not make `aoa-doctor` louder than readiness, and do not treat diagnostic
handoff candidates as completed repairs.

Validation:

```bash
python scripts/validate_stack.py
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python -m unittest tests.test_aoa_diagnose tests.test_diagnostic_spine_contracts tests.test_validate_stack_diagnostic_spine
bash -n scripts/aoa-doctor scripts/aoa-diagnose
```

