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
- `config-templates/Services/tos-graph/frontend/`
- `scripts/tos-up`
- `scripts/aoa-tos-graph`
- `mechanics/federation-seams/parts/tos-graph/tos_up.sh`
- `mechanics/federation-seams/parts/tos-graph/aoa_tos_graph.sh`

The active runtime route is:

- mount the real `Tree-of-Sophia` source checkout through `AOA_TOS_ROOT`
- read `ToS/derived-exports/tos_corpus_index.min.json`
- read `ToS/derived-exports/philosophy_graph_projection.min.json`
- expose switchable corpus and philosophy graph views through a localhost-only helper UI and API
- render the graph workbench through bundled WebGL frontends rather than an inline diagnostic SVG
- use `cosmos.gl` as the scale-oriented GPU renderer and keep Sigma as the
  curation/neighborhood renderer fallback
- stream philosophy projection scale-export tables for external large-graph
  viewers and analytics tools
- expose `tos-up` as the short operator command for the same workbench route; `aoa-tos-graph` remains the explicit stack command
- project the whole corpus index and philosophy graph projection into Neo4j when credentials are ready
- keep write mode absent by default

## Scale export route

The review workbench is intentionally not the final UI for the full future
Tree. It is the local operator lens for source-owned projection exports.

Large graph viewers should consume stable tables rather than scrape the UI or
treat Neo4j as source truth. `tos-graph` exposes these read-only tables:

- `/api/philosophy/scale-export/manifest`
- `/api/philosophy/scale-export/nodes.csv`
- `/api/philosophy/scale-export/nodes.jsonl`
- `/api/philosophy/scale-export/edges.csv`
- `/api/philosophy/scale-export/edges.jsonl`
- `/api/philosophy/scale-export/clusters.csv`
- `/api/philosophy/scale-export/clusters.jsonl`
- `/api/philosophy/scale-export/cluster-node-memberships.csv`
- `/api/philosophy/scale-export/cluster-node-memberships.jsonl`
- `/api/philosophy/scale-export/cluster-edge-memberships.csv`
- `/api/philosophy/scale-export/cluster-edge-memberships.jsonl`

Each endpoint accepts optional `view_id` and comma-separated `layers` query
parameters. The table spine is:

- nodes: `id`, `label`, `kind`, `view_ids`, `graph_layers`, source refs, properties
- edges: `id`, `source`, `target`, `predicate`, source refs, properties
- clusters: cluster identity and counts
- memberships: cluster-to-node and cluster-to-edge joins

This is the compatibility plane for scale tools such as GPU/WebGL graph
viewers, notebooks, offline layout experiments, and Neo4j import experiments.
It does not add ToS meaning, does not choose canon, and does not write back.
Corrections still route to `Tree-of-Sophia`, then ToS derived exports are
rebuilt and streamed again.

## Renderer route

`tos-graph` uses one filtered graph build path and two renderers:

- `cosmos.gl` consumes typed-array projections for larger graph layers and
  should be the first route for scale inspection
- Sigma consumes the same built graph for compact curation, neighborhood
  reading, and fallback behavior

Both renderers are runtime lenses. Neither owns graph meaning, source authority,
canonical status, or writeback.

## Layout route

The frontend reads ToS-owned `view_id` and `layout_hint` fields, then maps them
to runtime layout families:

- `timeline`: chronology and lane views
- `flow`: transmission corridors and canon-promotion flow
- `evidence`: source evidence, uncertainty, absence, and lost-corpus routes
- `semantic`: concept-lineage views
- `infrastructure`: institution, media, epigraphic, ritual-law, and parallel
  version views
- `organic`: fallback for views without a stronger shape

These families only choose coordinates, link styling, and whether the Cosmos
simulation may move the rendered points. They do not change ToS graph data and
must not be treated as canonical topology.

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
npm --prefix config-templates/Services/tos-graph/frontend run typecheck
npm --prefix config-templates/Services/tos-graph/frontend run build
```

Any later write-capable slice must also pass the relevant `Tree-of-Sophia`
validators before the route is considered honest.
