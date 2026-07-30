# AGENTS.md

## Applies to

This card applies to `mechanics/federation-seams/parts/memo-seam/`.

## Role

This part owns the runtime seam for bounded `aoa-memo` federation: public-safe
mirror refresh, read-only route-api inspection, and runtime candidate export.
Memo meaning stays in `aoa-memo`; this part owns only the stack-side adapter
route.

## Read before editing

1. `mechanics/federation-seams/AGENTS.md`
2. `README.md`
3. `docs/MEMO_RUNTIME_SEAM.md`
4. `scripts/aoa-sync-federation-surfaces`
5. `scripts/aoa-export-memo-candidate`
6. `schemas/active-organ-runtime-delivery-receipt.schema.json` when C20
   active-organ delivery evidence is in scope
7. `schemas/active-organ-canary-runtime-receipt.schema.json` and the exact
   canary runtime compatibility pin when the source-local Phase 8 lane is in
   scope
8. `schemas/active-organ-runtime-erasure-owner-extension-v0.schema.json` when
   ER4 runtime/cache/nervous-index or ER5 export/backup closure is in scope
9. `schemas/active-organ-agent-local-runtime-namespace-v0.schema.json` when
   Phase 12 local namespace isolation, expiry, rollback, or consumer-zero is
   in scope

## Runtime Routes

Refresh the public-safe memo mirror:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-memo
```

Inspect the memo seam after the `federation` profile is up:

```bash
curl http://127.0.0.1:5402/memo/registry
curl http://127.0.0.1:5402/memo/catalog
curl http://127.0.0.1:5402/memo/object-catalog
curl -X POST http://127.0.0.1:5402/memo/capsule -H 'content-type: application/json' -d '{"family":"doctrine","id":"AOA-M-0002"}'
```

Emit a bounded memo export candidate:

```bash
scripts/aoa-export-memo-candidate \
  --runtime-surface checkpoint_export \
  --input-file /tmp/checkpoint-export.json \
  --write
```

## Validation

```bash
python scripts/validate_stack.py
bash -n scripts/aoa-sync-federation-surfaces
python -m py_compile mechanics/governed-execution/parts/candidate-exports/aoa_export_memo_candidate.py
python -m pytest -q mechanics/federation-seams/parts/memo-seam/tests/test_active_organ_runtime_delivery_receipt.py
python -m pytest -q mechanics/federation-seams/parts/memo-seam/tests/test_active_organ_runtime_erasure.py
python -m pytest -q mechanics/federation-seams/parts/memo-seam/tests/test_active_organ_agent_local_runtime_namespace.py
```

## Closeout

Report whether the work touched mirror refresh, route-api inspection, or
candidate export, whether C20 runtime delivery receipt posture changed, and
state which `aoa-memo` source surfaces were consumed. If ER4/ER5 is in scope,
also report exact runtime versus backup surface coverage, recovery-probe
posture, residue, and whether live deletion remained false.
For Phase 12, report namespace isolation, local rollback/expiry,
consumer-zero, shared-organ availability, and whether live execution remained
false.
