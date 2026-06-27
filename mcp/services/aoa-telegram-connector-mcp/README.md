# aoa-telegram-connector-mcp

`aoa-telegram-connector-mcp` exposes the public
`aoa-telegram-connector` CLI through a read-only MCP service inside
`abyss-stack`.

It wraps these connector commands:

- `aoa-telegram doctor`
- `aoa-telegram storage status`
- `aoa-telegram policy check`
- `aoa-telegram query-graph`
- `aoa-telegram answer`

It deliberately does not expose connector commands that create or mutate local
state, including `init`, `materialize`, `build-index`, `build-graph`, account
login/session flows, imports, crawls, refreshes, or eval commands that
materialize proof fixtures.

## Tools

- `aoa_telegram_connector_status`
- `aoa_telegram_connector_source_route`
- `aoa_telegram_connector_query_graph`
- `aoa_telegram_connector_answer`

## Resources

- `aoa-telegram://source-route`
- `aoa-telegram://status`

## Configuration

Use an installed `aoa-telegram` binary or point the MCP package at a checkout:

```bash
export AOA_TELEGRAM_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-telegram-connector
export CONNECTOR_DATA_ROOT=/path/to/aoa-telegram-connector/data
export CONNECTOR_CACHE_ROOT=/path/to/aoa-telegram-connector/cache
export CONNECTOR_ARTIFACT_ROOT=/path/to/aoa-telegram-connector/artifacts
```

If `AOA_TELEGRAM_CONNECTOR_REPO` contains `src/aoa_telegram_connector/cli.py`,
the wrapper uses `python -m aoa_telegram_connector.cli` with `PYTHONPATH` set to
that checkout. Otherwise it calls `aoa-telegram` from `PATH`.

## Validate

```bash
python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py
python -m pytest mcp/services/aoa-telegram-connector-mcp/tests -q
```
