# Validation

Run:

```bash
python mcp/protocol-lab/scripts/build_protocol_lab_status.py
python mcp/protocol-lab/scripts/build_protocol_lab_status.py --check
python mcp/protocol-lab/scripts/validate_protocol_lab.py
python -m pytest -q mcp/protocol-lab/tests
python -m ruff check mcp/protocol-lab
```

The validator checks exact P1 gate order, the pre-final block, stable
registration retention, read-only pilot isolation, current SDK and stack pins,
Codex evidence limits, runtime-receipt absence, and generated-status
freshness.

Passing these commands proves only that the source gate is internally
consistent and fail-closed. It is not a runtime conformance, canary, consumer,
or rollback receipt.
