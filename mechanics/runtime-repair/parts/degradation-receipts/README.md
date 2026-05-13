# Degradation Receipts

Owns active service degradation receipt schemas, examples, and focused contract
tests.

The receipt payload keeps the `service_degradation_receipt_v1` schema version for
wire compatibility, but the active file route is the clean part-local surface:

- `schemas/service-degradation-receipt.schema.json`
- `examples/service-degradation-receipt*.example.json`
- `tests/test_degradation_receipts.py`
