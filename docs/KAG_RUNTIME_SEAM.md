# KAG RUNTIME SEAM

`abyss-stack` mirrors a bounded, public-safe advisory slice from `aoa-kag` and a source-owned handoff companion slice from `Tree-of-Sophia`.
This landing is advisory-only.
It does not turn the runtime into a live KAG query engine, a canon owner, or a reasoning authority.

## What is mirrored

From `aoa-kag`, the runtime mirrors:
- registry and federation spine surfaces
- reasoning handoff and recurrence regrounding packs
- tiny consumer bundle and technique-lift pack
- ToS retrieval-axis, text-chunk, and cross-source projection packs
- counterpart exposure review and supporting schemas/docs

From `tos-source`, the runtime mirrors:
- `generated/kag_export.min.json`
- `examples/source_node.example.json`
- `examples/tos_tiny_entry_route.example.json`
- the small source-owned docs and schemas that explain those surfaces

The mirrored runtime paths are:
- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/`
- `${AOA_STACK_ROOT}/Knowledge/federation/tos-source/`

The sync step is explicit:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
```

## What `/kag/*` exposes

The localhost-only `route-api` exposes raw and structured advisory reads under `/kag/*`.

Raw reads include:
- `/kag/registry`
- `/kag/federation-spine`
- `/kag/tiny-consumer-bundle`
- `/kag/reasoning-handoff-pack`
- `/kag/return-regrounding-pack`
- `/kag/technique-lift-pack`
- `/kag/tos-retrieval-axis-pack`
- `/kag/tos-text-chunk-map`
- `/kag/cross-source-node-projection`
- `/kag/counterpart-exposure-review`
- `/kag/tos-export`
- `/kag/tos-entry-surface`

Structured reads include:
- `/kag/inspect`
- `/kag/query-mode`
- `/kag/regrounding`
- `/kag/repo-entry`
- `/kag/chunk`
- `/kag/axis`
- `/kag/projection`

These surfaces let the runtime inspect derived retrieval/regrounding metadata and inspect the `Tree-of-Sophia` handoff companion without mutating either side.

## Why `tos-source` is mirrored separately

`aoa-kag` owns derived retrieval and handoff packs.
It does not own `Tree-of-Sophia` canon.

The runtime therefore mirrors `tos-source` as a source-owned companion so the `Tree-of-Sophia` export remains visibly source-authored rather than being collapsed into a KAG-owned payload.
That keeps the authority boundary legible:
- `aoa-kag` provides derived retrieval/regrounding surfaces
- `Tree-of-Sophia` remains the source-owned handoff authority

## What this phase does not do

This phase is advisory-only and intentionally does not add:
- live KAG querying
- runtime reasoning execution
- graph traversal beyond mirrored pack contents
- source mutation
- memo writeback
- eval verdict logic
- canon authorship

It is a runtime inspection seam, not a live retrieval engine.
