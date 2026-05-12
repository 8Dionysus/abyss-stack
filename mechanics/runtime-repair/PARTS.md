# Runtime Repair Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Degradation receipts | `parts/degradation-receipts/` | `legacy/artifacts/schemas/service_degradation_receipt_v1.json`, `legacy/artifacts/examples/service_degradation_receipt*.json` |
| Repair-safe closeout | `parts/repair-safe-closeout/` | `mechanics/runtime-repair/docs/REPAIR_SAFE_CLOSEOUT.md`, `legacy/artifacts/schemas/repair_safe_closeout_receipt_v1.json`, `legacy/artifacts/examples/repair_safe_closeout_receipt*.json` |
| Runtime chaos | `parts/runtime-chaos/` | `legacy/raw/RUNTIME_CHAOS_WAVE1.md` |
| Antifragility posture | `parts/antifragility-posture/` | `mechanics/runtime-repair/docs/ANTIFRAGILITY_RUNTIME.md`, `mechanics/runtime-repair/docs/VIA_NEGATIVA_CHECKLIST.md` |
| A2A return dry-run | `parts/a2a-return-dry-run/` | `mechanics/runtime-repair/docs/A2A_RETURN_DRY_RUN.md`, `scripts/aoa-a2a-return-closeout-dry-run`, active schema, example, and focused tests |
| Memo contradiction sidecar | `parts/memo-contradiction-sidecar/` | `scripts/aoa-run-memo-contradiction-integrity`, focused sidecar tests |

Old wave and `_v1` receipt surfaces are now package-local legacy. Active repair
work should start at `README.md`, `DIRECTION.md`, and `PROVENANCE.md`.
