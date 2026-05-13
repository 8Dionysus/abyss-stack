# Runtime Repair Legacy Index

## Raw Docs

Old root docs now live in `legacy/raw/`:

- `docs/RUNTIME_CHAOS_WAVE1.md`

## Artifact Bridge

Old root artifact names map to active part-local homes:

- `schemas/service_degradation_receipt_v1.json` -> `../parts/degradation-receipts/schemas/service-degradation-receipt.schema.json`
- `examples/service_degradation_receipt*.json` -> `../parts/degradation-receipts/examples/service-degradation-receipt*.example.json`
- `tests/test_antifragility_contracts.py` -> `../parts/degradation-receipts/tests/test_degradation_receipts.py` and `../parts/repair-safe-closeout/tests/test_repair_safe_closeout_receipts.py`
- `schemas/repair_safe_closeout_receipt_v1.json` -> `../parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json`
- `examples/repair_safe_closeout_receipt*.json` -> `../parts/repair-safe-closeout/examples/repair-safe-closeout-receipt*.example.json`

## Active Bridge

Start at `../README.md` and the owning part. Use legacy raw files for lineage,
not as the first active runtime repair route.
