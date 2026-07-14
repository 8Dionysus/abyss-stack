# AoA 4PDA Connector MCP Design

## Purpose

Expose already-built local 4PDA connector evidence to agents through MCP while
keeping the source connector repository and heavy generated data outside
`abyss-stack`.

## Shape

The package discovers either:

- an installed `aoa-4pda` executable, or
- a connector checkout from `AOA_4PDA_CONNECTOR_REPO`.

It calls the connector CLI without a shell, parses JSON stdout, and wraps the
result in MCP-specific packets. The wrapper passes through configured
`CONNECTOR_DATA_ROOT`, `CONNECTOR_CACHE_ROOT`, and `CONNECTOR_ARTIFACT_ROOT`.

The first surface is read-only:

- `status`: doctor, storage, and readiness evidence;
- `source_route`: service name, env vars, owner split, wrapped commands, and
  stop lines;
- `query_graph` and `query_hybrid`: local query packets from existing runs;
- `answer`: compact answer packet preserving source answer fields.

## Authority

The MCP package owns access behavior only. It does not own 4PDA policy, crawl
permission, normalized post shape, index semantics, graph semantics, answer
semantics, or generated storage. Runtime consumers must treat source URLs,
post ids, evidence refs, receipts, freshness, and connector JSON packets as the
stronger authority.

## Non-goals

- No crawl, refresh-build, materialize, reindex, seed-edit, approval, or write
  tools.
- No network access from answer/query/status paths.
- No internal 4PDA search or private/account routes.
- No remote, wildcard-bind, gateway, or proxy exposure. The only long-running
  route is the source-owned authenticated loopback shared HTTP owner from
  `ABYSS-STACK-D-0077`; stdio remains the portable default.
