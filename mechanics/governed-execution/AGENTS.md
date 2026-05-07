# AGENTS.md

Applies to `mechanics/governed-execution/`.

This package owns the route shape for governed local-worker execution,
autonomy-gate reporting, return policy, candidate export, and reviewable run
records.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`, and
`PARTS.md` before editing.

Do not turn advisory execution into autonomous authority. Do not bypass gates,
review records, or owner handoffs.

Validation:

```bash
python scripts/validate_stack.py
python -m unittest tests.test_governed_execution
python -m py_compile scripts/_aoa_governed_execution.py scripts/_aoa_status_autonomy.py
bash -n scripts/aoa-governed-run scripts/aoa-status scripts/aoa-export-memo-candidate scripts/aoa-export-artifact-hook-candidate
```

