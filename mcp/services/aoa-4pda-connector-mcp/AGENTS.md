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
| check | `python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py`, `python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q` |

## Boundaries

- Keep `aoa-4pda-connector` canonical for source policy, parser, normalizer,
  index, graph, answer packet, readiness, and storage contracts.
- Keep `abyss-stack` responsible only for MCP packaging, stdio runtime access,
  stack validation, and deployment posture.
- Do not expose crawl, refresh-build, materialize, reindex, seed-edit, or write
  tools in this first slice.
- Do not call 4PDA internal search, network routes, login/private/QMS/post,
  attach, or download routes from MCP.
- Do not commit corpora, raw captures, indexes, vectors, graphs, sqlite,
  parquet, qdrant, lancedb, receipts, or caches here.
- MCP packets are access aids, not source truth.

## Validation

Run:

```bash
python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q
```

For parent MCP route changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

For a local OS Abyss smoke with a materialized connector run:

```bash
AOA_4PDA_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-4pda-connector \
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q

PYTHONPATH=mcp/services/aoa-4pda-connector-mcp/src \
AOA_4PDA_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-4pda-connector \
python -m aoa_4pda_connector_mcp.cli answer \
  "Xiaomi 13T recovery.img fastboot TWRP" \
  --run 20260621T194521Z__crawl \
  --limit 5
```
