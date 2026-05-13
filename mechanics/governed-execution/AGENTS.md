# AGENTS.md

Applies to `mechanics/governed-execution/`.

This package owns the route shape for governed local-worker execution,
autonomy-gate reporting, return policy, candidate export, and reviewable run
records.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not turn advisory execution into autonomous authority. Do not bypass gates,
review records, or owner handoffs.

Validation:

```bash
python scripts/validate_stack.py
python -m pytest mechanics/governed-execution/parts/governed-runner/tests/test_governed_execution.py mechanics/governed-execution/parts/candidate-exports/tests/test_runtime_eval_evidence_export.py -q
python -m py_compile mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py mechanics/governed-execution/parts/candidate-exports/aoa_export_memo_candidate.py mechanics/governed-execution/parts/candidate-exports/aoa_export_runtime_evidence_selection.py mechanics/governed-execution/parts/candidate-exports/aoa_export_artifact_hook_candidate.py
bash -n scripts/aoa-status
```
