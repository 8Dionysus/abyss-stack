# TOS_GRAPH_CURATION

## Purpose

This note defines the owner-repo contract for a corpus and philosophy graph
curation surface in `abyss-stack`.

The surface belongs here only as runtime body, helper UI, compose/profile
posture, and Neo4j projection logic.
It does not move ToS canonical meaning into `abyss-stack`.

## Source and authority split

- `Tree-of-Sophia` remains the canonical source of truth for authored nodes,
  source refs, relation packs, registries, validator law, the checked
  whole-corpus index, and the materialized philosophy graph projection
- `abyss-stack` may project those derived exports into Neo4j and present them
  through a localhost helper service and MCP access planes
- Neo4j stays a projection and query surface only
- mirrored `tos-source` federation surfaces stay advisory and must not be
  treated as canonical edit input

## Intended runtime shape

The planned helper surface is `tos-graph`.

The first-class repo-local anchors for this slice are:

- `compose/modules/52-tos-graph.yml`
- `compose/profiles/curation.txt`
- `config-templates/Configs/tos-graph/config.yaml`
- `config-templates/Services/tos-graph/`
- `scripts/tos-up`
- `scripts/aoa-tos-graph`
- `mechanics/federation-seams/parts/tos-graph/tos_up.sh`
- `mechanics/federation-seams/parts/tos-graph/aoa_tos_graph.sh`

The active runtime route is:

- mount the real `Tree-of-Sophia` source checkout through `AOA_TOS_ROOT`
- read `ToS/derived-exports/tos_corpus_index.min.json`
- read `ToS/derived-exports/philosophy_graph_projection.min.json`
- expose switchable corpus and philosophy graph views through a localhost-only helper UI and API
- expose `tos-up` as the short operator command for the same workbench route; `aoa-tos-graph` remains the explicit stack command
- project the whole corpus index and philosophy graph projection into Neo4j when credentials are ready
- keep write mode absent by default

## Dry-run-first landing order

This owner-repo landing stays projection-first:

1. define the derived graph contracts in Tree of Sophia
2. expose the read-only corpus and philosophy graph surfaces in `abyss-stack`
3. verify projection sync, graph-view posture, and localhost bind
4. keep curation-profile launch narrow even when unrelated machine-fit overlays exist
5. only then consider any validator-gated write route as a separate reviewed change

The current landed slice is derived-export driven. Writeback remains
intentionally absent.

Do not jump straight to canonical writeback from a staging bundle.

## Writeback boundary

Any later write path must keep these conditions explicit:

- `Tree-of-Sophia` validators run after apply and before reproject
- failed validation restores the prior file state before reporting failure
- relation edits preserve canonical-pack and intake-ledger parity where the
  current route uses both surfaces
- `predicate_id` remains registry-backed rather than free-form in the first
  pass

## Initial non-goals

- no host exposure beyond `127.0.0.1`
- no direct claim that Neo4j stores canonical truth
- no autonomous write routes into ToS canon
- no hidden git commits
- no whole-corpus force-graph default
- no fallback to the old root-level `tree/` route model

## Verification posture

The first owner-repo slice should verify with:

```bash
scripts/tos-up --no-open --no-wait
scripts/aoa-tos-graph --no-open --no-wait
scripts/aoa-tos-graph --status
python scripts/validate_stack.py
scripts/aoa-profile-modules --profile curation --paths
scripts/aoa-profile-endpoints --profile curation
scripts/aoa-profile-modules --profile substrate --profile curation --paths
scripts/aoa-profile-endpoints --profile substrate --profile curation
```

Any later write-capable slice must also pass the relevant `Tree-of-Sophia`
validators before the route is considered honest.
