# AGENTS.md

## AoA Telegram Connector MCP

This card applies to `mcp/services/aoa-telegram-connector-mcp/`.

## Responsibility

`aoa-telegram-connector-mcp` is the abyss-stack runtime access plane for the
public `aoa-telegram-connector` repository. It exposes already-built local
Telegram connector evidence to agents through MCP without owning Telegram source
policy, parser logic, index construction, graph construction, or generated data.

## Contract

| surface | rule |
| --- | --- |
| input | installed `aoa-telegram` CLI or `AOA_TELEGRAM_CONNECTOR_REPO` checkout |
| output | MCP packets for status, source-route, graph query, and answer |
| owner | this card owns MCP wrapping; `aoa-telegram-connector` owns connector truth |
| storage | heavy connector state lives under connector storage roots, not in abyss-stack |
| checks | `python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py`, `python -m pytest mcp/services/aoa-telegram-connector-mcp/tests -q` |

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
- HTTP uses the exact Telegram read credential, scope, client identity, and a
  managed no-write/no-network contour on loopback.

## Validation

Run package-local checks after changes:

```bash
python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py
python -m pytest mcp/services/aoa-telegram-connector-mcp/tests -q
```

For source-route changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python scripts/ci_gate.py --mode source-fast
python scripts/ci_gate.py --mode mcp-services
```

## Local Smoke

```bash
PYTHONPATH=mcp/services/aoa-telegram-connector-mcp/src \
AOA_TELEGRAM_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-telegram-connector \
python -m aoa_telegram_connector_mcp.cli source-route
```
