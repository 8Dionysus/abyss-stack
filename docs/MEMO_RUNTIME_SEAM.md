# MEMO RUNTIME SEAM

This document defines the `abyss-stack` landing for `aoa-memo` in the runtime body.

It does not turn `abyss-stack` into the memory authority layer.
It defines how the runtime may mirror public-safe memo surfaces, inspect them through the existing `route-api`, and export bounded memo candidate artifacts without promoting them automatically.

## What is mirrored

The Phase 3 memo landing mirrors a bounded public-safe subset of `aoa-memo` into:

`${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/`

That mirror currently includes:

- memo doctrine docs needed for runtime orientation and recurrence support
- compact doctrine and object catalogs
- full section packs for doctrine and object inspection
- router-ready and object-facing recall contracts
- the checkpoint-to-memory contract example
- the core memory and checkpoint-to-memory schemas

The mirror is runtime-local and exact for its allowlisted subtree.
It is not a loose copy of the whole `aoa-memo` repository.

## What `route-api` exposes

The existing localhost-only `route-api` remains the single federation facade on `127.0.0.1:5402`.

Phase 3 adds a `/memo/*` namespace for bounded read-only inspection:

- `GET /memo/registry`
- `GET /memo/catalog`
- `GET /memo/object-catalog`
- `GET /memo/checkpoint-contract`
- `POST /memo/inspect`
- `POST /memo/expand`
- `POST /memo/recall-contract`
- `POST /memo/writeback-map`

These surfaces are advisory and read-only.
They do not access live scratchpad, do not perform free-text recall, do not write into `aoa-memo`, and do not replace memo-owned authority.

## What the runtime exports

The runtime export seam is filesystem-first.

`scripts/aoa-export-memo-candidate` reads the mirrored checkpoint-to-memory contract and emits bounded runtime-owned candidate artifacts under:

- `${AOA_STACK_ROOT}/Logs/memo-exports/latest/`
- `${AOA_STACK_ROOT}/Logs/memo-exports/records/`

These artifacts are reviewable candidates, not memo objects.
They are the runtime-side handoff pack for possible future import or review in `aoa-memo`.

The export seam maps only the currently mirrored contract surfaces:

- `checkpoint_export`
- `approval_record`
- `transition_record`
- `execution_trace`
- `review_trace`
- `distillation_claim_candidate`
- `distillation_pattern_candidate`
- `distillation_bridge_candidate`

## What this phase does not do

This phase does not:

- auto-write memo objects from runtime traffic
- add a new host-facing port
- add a new writeback HTTP API
- make `langchain-api` write memory artifacts implicitly
- turn `abyss-stack` into the live memory store
- override `aoa-memo` object canon, review posture, or recall meaning

## Operational usage

To refresh the public-safe memo mirror:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-memo
```

To inspect the memo seam after the `federation` profile is up:

```bash
curl http://127.0.0.1:5402/memo/registry
curl http://127.0.0.1:5402/memo/catalog
curl http://127.0.0.1:5402/memo/object-catalog
```

To emit a bounded memo export candidate:

```bash
scripts/aoa-export-memo-candidate \
  --runtime-surface checkpoint_export \
  --input-file /tmp/checkpoint-export.json \
  --write
```

## One-line rule

`abyss-stack` may mirror `aoa-memo`, inspect its bounded recall surfaces, and emit runtime memo candidates, but it must not silently become `aoa-memo`.
