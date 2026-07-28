# Discord Connector MCP Design

## Purpose

Expose already-built local Discord connector evidence to agents through MCP
while preserving source ownership in `aoa-discord-connector`.

## Shape

The service is a thin adapter over either:

- an installed `aoa-discord` executable, or
- a local `AOA_DISCORD_CONNECTOR_REPO` checkout.

It returns MCP packets that keep the connector's source packet schema, command
brief, evidence chain, permission report, answer report, conflict/freshness/
applicability/warning reports, and local-search policy.

## Non-Goals

- No crawling, imports, account login, session mutation, fixture materialization,
  index building, graph building, or refresh from MCP.
- No generated connector state in Git.
- No hidden promotion of MCP output above connector packet truth.

## Failure Model

The wrapper marks packets as `error` when connector output does not prove local,
read-only behavior, especially when `network_touched=false` or
`policy.internal_search_used=false` is missing.

The HTTP lifecycle uses an exact Discord read credential and a read-only,
no-network managed process rather than the compatibility shared contour.
