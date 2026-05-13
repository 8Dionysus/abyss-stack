# AGENTS.md

Applies to `mechanics/runtime-repair/`.

This package owns the route shape for degradation receipts, legacy chaos runtime
recovery, repair-safe closeout, A2A return closeout dry-run, and bounded
antifragility runtime posture.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing. Use `PROVENANCE.md` and
`legacy/INDEX.md` before editing moved receipt artifacts.

Do not perform repair, delete data, or claim recovery from a receipt. This
package shapes runtime evidence and handoff only.

Validation:

```bash
python scripts/validate_stack.py
python -m pytest mechanics/runtime-repair/legacy/artifacts/tests mechanics/runtime-repair/parts/a2a-return-dry-run/tests/test_a2a_return_closeout_dry_run.py mechanics/runtime-repair/parts/memo-contradiction-sidecar/tests/test_memo_contradiction_integrity_runner.py
bash -n scripts/aoa-a2a-return-closeout-dry-run scripts/aoa-run-memo-contradiction-integrity
```
