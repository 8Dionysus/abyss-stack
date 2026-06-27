# aoa-discord-connector-mcp

`aoa-discord-connector-mcp` exposes the public
`aoa-discord-connector` CLI through a read-only MCP service inside
`abyss-stack`.

It wraps these connector commands:

- `aoa-discord doctor`
- `aoa-discord storage status`
- `aoa-discord policy check`
- `aoa-discord query-graph`
- `aoa-discord answer`

It deliberately does not expose connector commands that create or mutate local
state, including `init`, `materialize`, `build-index`, `build-graph`, account
login/session flows, imports, crawls, refreshes, or eval commands that
materialize proof fixtures.

## Tools

- `aoa_discord_connector_status`
- `aoa_discord_connector_source_route`
- `aoa_discord_connector_query_graph`
- `aoa_discord_connector_answer`

## Resources

- `aoa-discord://source-route`
- `aoa-discord://status`

## Configuration

Use an installed `aoa-discord` binary or point the MCP package at a checkout:

```bash
export AOA_DISCORD_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-discord-connector
export CONNECTOR_DATA_ROOT=/path/to/aoa-discord-connector/data
export CONNECTOR_CACHE_ROOT=/path/to/aoa-discord-connector/cache
export CONNECTOR_ARTIFACT_ROOT=/path/to/aoa-discord-connector/artifacts
```

If `AOA_DISCORD_CONNECTOR_REPO` contains `src/aoa_discord_connector/cli.py`,
the wrapper uses `python -m aoa_discord_connector.cli` with `PYTHONPATH` set to
that checkout. Otherwise it calls `aoa-discord` from `PATH`.

## Validate

```bash
python mcp/services/aoa-discord-connector-mcp/scripts/validate_discord_connector_mcp.py
python -m pytest mcp/services/aoa-discord-connector-mcp/tests -q
```
