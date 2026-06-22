# AoA 4PDA Connector MCP

`aoa-4pda-connector-mcp` exposes the public `aoa-4pda-connector` CLI through a
stack-owned, read-only MCP access plane.

It wraps:

- `aoa-4pda doctor`
- `aoa-4pda storage status`
- `aoa-4pda ready`
- `aoa-4pda query-graph`
- `aoa-4pda query-hybrid`
- `aoa-4pda answer`

It returns:

- connector status and storage evidence
- source-route and owner-boundary notes
- graph/hybrid query packets
- compact answer packets preserving `agent_answer`, `evidence_chain`,
  `nuance_report`, `answer_report`, and `network_touched=false`

## Boundary

`aoa-4pda-connector` owns 4PDA-specific source policy, local data contracts,
CLI behavior, schemas, and answer packet semantics. `abyss-stack` owns this MCP
runtime package and stdio access. Generated corpora, indexes, vectors, graphs,
receipts, and caches remain outside Git.

## Configuration

Use an installed `aoa-4pda` binary or point the MCP package at a checkout:

```bash
export AOA_4PDA_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-4pda-connector
export CONNECTOR_DATA_ROOT=/path/to/aoa-4pda-connector/data
export CONNECTOR_CACHE_ROOT=/path/to/aoa-4pda-connector/cache
export CONNECTOR_ARTIFACT_ROOT=/path/to/aoa-4pda-connector/artifacts
```

When `AOA_4PDA_CONNECTOR_REPO` points at a checkout with `src/`, the wrapper
uses `python -m aoa_4pda_connector.cli` with `PYTHONPATH` set to that checkout.
Otherwise it calls `aoa-4pda` from `PATH`.

## Local Checks

```bash
python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q
```
