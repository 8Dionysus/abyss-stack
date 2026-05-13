# AGENTS.md

Applies to `mechanics/diagnostic-spine/`.

This package owns the route shape for doctor readiness, status truth goals,
diagnostic bundle output, last-good anchors, and repair handoff candidates.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not make `aoa-doctor` louder than readiness, and do not treat diagnostic
handoff candidates as completed repairs.

Validation:

```bash
python scripts/validate_stack.py
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python -m pytest mechanics/diagnostic-spine/parts/diagnose-wrapper/tests/test_aoa_diagnose.py mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_validate_stack_diagnostic_spine.py -q
bash -n scripts/aoa-doctor scripts/aoa-diagnose
bash -n mechanics/diagnostic-spine/parts/doctor-readiness/aoa_doctor.sh mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.sh
```
