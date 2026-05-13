# Repair-Safe Closeout

Routes `mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md` plus active
repair-safe closeout receipt schemas, examples, and focused contract tests.

This part owns closeout posture. It does not perform live repair.

The receipt payload keeps the `repair_safe_closeout_receipt_v1` schema version
for wire compatibility, but the active file route is the clean part-local
surface:

- `schemas/repair-safe-closeout-receipt.schema.json`
- `examples/repair-safe-closeout-receipt*.example.json`
- `tests/test_repair_safe_closeout_receipts.py`
