# AGENTS.md

## Applies to

This card applies to `mcp/services/aoa-4pda-connector-mcp/`.

## Role

`aoa-4pda-connector-mcp` is a thin MCP access plane over the public
`aoa-4pda-connector` CLI and local JSON packets. It exposes status, source
route, graph/hybrid query packets, and answer packets without moving 4PDA
source authority or generated corpora into `abyss-stack`.
Answer packets must preserve `agent_answer`, evidence-chain fields, and
`network_touched=false`.

## Operating Card

| Field | Route |
| --- | --- |
| role | read-only MCP access plane for 4PDA connector packets |
| input | installed `aoa-4pda` CLI or `AOA_4PDA_CONNECTOR_REPO` checkout |
| output | status, source-route, query, and answer packets |
| owner | `mcp/services/aoa-4pda-connector-mcp/AGENTS.md` for access-plane behavior; `aoa-4pda-connector` owns connector truth |
| next route | connector packet -> MCP packet -> agent answer/review route |
| tools | `aoa_4pda_connector_mcp.core`, `aoa_4pda_connector_mcp.server`, `scripts/validate_4pda_connector_mcp.py` |
| check | on-demand package validation route in `VALIDATION.md` |

## Boundaries

- Keep `aoa-4pda-connector` canonical for source policy, parser, normalizer,
  index, graph, answer packet, readiness, and storage contracts.
- Keep `abyss-stack` responsible only for MCP packaging, local transport
  access, stack validation, and deployment posture. Stdio remains the portable
  default; optional HTTP uses the exact 4PDA read bearer, scope, and client
  identity on loopback under `ABYSS-STACK-D-0077`.
- Do not expose crawl, refresh-build, materialize, reindex, seed-edit, or write
  tools in this first slice.
- Do not call 4PDA internal search, network routes, login/private/QMS/post,
  attach, or download routes from MCP.
- Do not commit corpora, raw captures, indexes, vectors, graphs, sqlite,
  parquet, qdrant, lancedb, receipts, or caches here.
- MCP packets are access aids, not source truth.
- The managed read contour has no persistent writable filesystem path and
  denies non-loopback IP traffic.

## Validation

Run:

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For parent MCP route changes, alsouse the on-demand validation route in `VALIDATION.md`.


For a local OS Abyss smoke with a materialized connectoruse the on-demand validation route in `VALIDATION.md`.
