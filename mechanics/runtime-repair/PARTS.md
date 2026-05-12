# Runtime Repair Parts

| Part | Current source surfaces |
|---|---|
| Degradation receipts | `legacy/artifacts/schemas/service_degradation_receipt_v1.json`, `legacy/artifacts/examples/service_degradation_receipt*.json` |
| Repair-safe closeout | `docs/REPAIR_SAFE_CLOSEOUT.md`, `legacy/artifacts/schemas/repair_safe_closeout_receipt_v1.json`, `legacy/artifacts/examples/repair_safe_closeout_receipt*.json` |
| Runtime chaos | `legacy/raw/RUNTIME_CHAOS_WAVE1.md` |
| Antifragility posture | `docs/ANTIFRAGILITY_RUNTIME.md`, `docs/VIA_NEGATIVA_CHECKLIST.md` |
| A2A return dry-run | `docs/A2A_RETURN_DRY_RUN.md`, `scripts/aoa-a2a-return-closeout-dry-run`, matching schema and example |
| Memo contradiction sidecar | `scripts/aoa-run-memo-contradiction-integrity`, related examples and tests |

Old wave and `_v1` receipt surfaces are now package-local legacy. Active repair
work should start at `README.md`, `DIRECTION.md`, and `PROVENANCE.md`.
