# TOS_GRAPH_CURATION

## Purpose

This note defines the initial owner-repo contract for a route-first ToS graph
curation surface in `abyss-stack`.

The surface belongs here only as runtime body, helper UI, compose/profile
posture, and Neo4j projection logic.
It does not move ToS canonical meaning into `abyss-stack`.

## Source and authority split

- `Tree-of-Sophia` remains the canonical source of truth for authored nodes,
  relation packs, registries, and validator law
- `abyss-stack` may project those surfaces into Neo4j and present them through
  a localhost helper service
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

The bounded first route is:

- mount the real `Tree-of-Sophia` source checkout through `AOA_TOS_ROOT`
- read canonical tree and relation-pack inputs
- project a route-first slice into Neo4j
- expose a localhost-only helper UI and API
- keep write mode off by default

## Dry-run-first landing order

This owner-repo landing stays preview-first:

1. define the contract and quest anchors
2. land a read-only vertical slice
3. verify route-first projection, inspector posture, and localhost bind
4. keep curation-profile launch narrow even when unrelated machine-fit overlays exist
5. only then consider validator-gated patch preview and apply

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

## Verification posture

The first owner-repo slice should verify with:

```bash
python scripts/validate_stack.py
scripts/aoa-profile-modules --profile curation --paths
scripts/aoa-profile-endpoints --profile curation
scripts/aoa-profile-modules --profile core --profile curation --paths
scripts/aoa-profile-endpoints --profile core --profile curation
```

Any later write-capable slice must also pass the relevant `Tree-of-Sophia`
validators before the route is considered honest.
