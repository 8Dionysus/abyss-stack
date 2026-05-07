# AGENTS.md

Applies to `mechanics/runtime-repair/`.

This package owns the route shape for degradation receipts, chaos-wave runtime
recovery, repair-safe closeout, A2A return closeout dry-run, and bounded
antifragility runtime posture.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`, and
`PARTS.md` before editing.

Do not perform repair, delete data, or claim recovery from a receipt. This
package shapes runtime evidence and handoff only.

Validation:

```bash
python scripts/validate_stack.py
python -m unittest tests.test_antifragility_contracts tests.test_a2a_return_closeout_dry_run tests.test_memo_contradiction_integrity_runner
bash -n scripts/aoa-a2a-return-closeout-dry-run scripts/aoa-run-memo-contradiction-integrity
```

