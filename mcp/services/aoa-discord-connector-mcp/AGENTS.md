# AGENTS.md

## AoA Discord Connector MCP

This card applies to `mcp/services/aoa-discord-connector-mcp/`.

## Responsibility

`aoa-discord-connector-mcp` is the abyss-stack runtime access plane for the
public `aoa-discord-connector` repository. It exposes already-built local
Discord connector evidence to agents through MCP without owning Discord source
policy, parser logic, index construction, graph construction, or generated data.

## Contract

| surface | rule |
| --- | --- |
| input | installed `aoa-discord` CLI or `AOA_DISCORD_CONNECTOR_REPO` checkout |
| output | MCP packets for status, source-route, graph query, and answer |
| owner | this card owns MCP wrapping; `aoa-discord-connector` owns connector truth |
| storage | heavy connector state lives under connector storage roots, not in abyss-stack |
| checks | on-demand package validation route in `VALIDATION.md` |

## Hard Boundaries

- Keep this MCP service read-only.
- Do not expose `init`, `materialize`, `build-index`, `build-graph`, crawl,
  import, account login, or session mutation through MCP tools.
- Preserve connector packet fields that agents need for grounded answers:
  `evidence_chain`, `permission_report`, `answer_report`, `conflict_report`,
  `freshness_report`, `applicability_report`, `warning_report`, and `policy`.
- Do not write corpora, exports, indexes, vectors, graphs, receipts, caches, or
  account/session files into this repository.
- Treat `network_touched=false` and local packet provenance as boundary evidence,
  not as decorative metadata.
- HTTP uses the exact Discord read credential, scope, client identity, and a
  managed no-write/no-network contour on loopback.

## Validation

Run package-local checks after changes:

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For source-route changes, alsouse the on-demand validation route in `VALIDATION.md`.


## Local Smoke
