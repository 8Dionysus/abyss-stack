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
```

## Closeout

Report whether the work touched mirror refresh, route-api inspection, or
candidate export, and state which `aoa-memo` source surfaces were consumed.
