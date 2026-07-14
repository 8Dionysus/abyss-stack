# Telegram and Discord Connector MCP Access Planes

- Decision ID: ABYSS-STACK-D-0074
- Status: accepted
- Date: 2026-06-26
- Owner surface: `mcp/services/aoa-telegram-connector-mcp/`, `mcp/services/aoa-discord-connector-mcp/`

## Index Metadata

- Original date: 2026-06-26
- Surface classes: MCP access plane, source/runtime boundary, connector federation
- Stack lanes: MCP services, federation seams
- Mechanic parents: federation-seams
- Guard families: MCP port confinement, read-only access plane, source/runtime boundary, source-structure
- Posture: accepted Telegram and Discord connector MCP access-plane rationale

## Context

`aoa-telegram-connector` and `aoa-discord-connector` are separate public
connector repositories. They own source policy, permission modes, schemas,
storage contracts, fixture materialization, index/graph construction, and answer
packet semantics for their source families.

`abyss-stack` owns local runtime MCP services. Agents need stack-native MCP
access to already-built local Telegram and Discord evidence without making the
stack repository own connector truth or heavy generated state.

The connector CLIs include some commands that look evaluative but are not
read-only: `eval permissions` materializes proof fixtures. Exposing those
commands through MCP would blur the access-plane boundary and allow a read path
to mutate connector state.

## Options considered

1. Keep Telegram and Discord connector access as direct CLI calls only.
2. Put MCP servers inside each public connector repository only.
3. Add stack-owned MCP service packages that wrap only read-only connector
   commands.
4. Expose broader connector eval/build commands through MCP for convenience.

## Decision

Choose option 3.

Add `mcp/services/aoa-telegram-connector-mcp/` and
`mcp/services/aoa-discord-connector-mcp/` as stack-owned runtime MCP packages.
Each package wraps the connector CLI with a checkout-aware working directory,
parses JSON stdout, and exposes local-only status, source-route, graph query,
and answer tools/resources.

Do not expose crawl, import, login/session mutation, `init`, `materialize`,
`build-index`, `build-graph`, refresh, or connector eval commands through these
MCP services. Permission modes are declared in `source-route`; concrete
permission evidence stays in connector `permission_report` fields returned by
query and answer packets.

## Rationale

This keeps the topology aligned with the connector-family split: public
connector repositories stay portable and source-owned, while `abyss-stack`
provides the local MCP runtime access plane used by OS Abyss.

The read-only slice is enough for agents to ask questions over built local
evidence and receive permission-aware answer packets. Avoiding connector eval
commands prevents a status or inspection path from quietly writing generated
proof state.

## Consequences

- Agents get stack-native MCP routes for Telegram and Discord local evidence.
- The services depend on connector CLIs and storage roots being configured.
- Missing local indexes or graphs are reported by connector packets; MCP does
  not repair or build them.
- Future write/build/eval/network tools require a separate decision and a
  source-side connector contract that explicitly permits that expansion.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-telegram-connector-mcp/AGENTS.md`
- `mcp/services/aoa-telegram-connector-mcp/DESIGN.md`
- `mcp/services/aoa-telegram-connector-mcp/README.md`
- `mcp/services/aoa-telegram-connector-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-telegram-connector-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-telegram-connector-mcp/src/aoa_telegram_connector_mcp/core.py`
- `mcp/services/aoa-telegram-connector-mcp/src/aoa_telegram_connector_mcp/server.py`
- `mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py`
- `mcp/services/aoa-telegram-connector-mcp/tests/test_telegram_connector_mcp.py`
- `mcp/services/aoa-discord-connector-mcp/AGENTS.md`
- `mcp/services/aoa-discord-connector-mcp/DESIGN.md`
- `mcp/services/aoa-discord-connector-mcp/README.md`
- `mcp/services/aoa-discord-connector-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-discord-connector-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-discord-connector-mcp/src/aoa_discord_connector_mcp/core.py`
- `mcp/services/aoa-discord-connector-mcp/src/aoa_discord_connector_mcp/server.py`
- `mcp/services/aoa-discord-connector-mcp/scripts/validate_discord_connector_mcp.py`
- `mcp/services/aoa-discord-connector-mcp/tests/test_discord_connector_mcp.py`
- `aoa-telegram-connector:docs/MCP_ROLLOUT.md`
- `aoa-telegram-connector:docs/RUNTIME_CONTRACT.md`
- `aoa-discord-connector:docs/MCP_ROLLOUT.md`
- `aoa-discord-connector:docs/RUNTIME_CONTRACT.md`

## Follow-up route

Use each connector service `AGENTS.md`, the parent MCP route, the decision
district route, and root validation. Those active owners retain the exact
commands.

For local OS Abyss smoke, point `AOA_TELEGRAM_CONNECTOR_REPO` and
`AOA_DISCORD_CONNECTOR_REPO` at the connector checkouts and run MCP `status`.
Run `answer` or `query-graph` only against an existing materialized connector
run.
