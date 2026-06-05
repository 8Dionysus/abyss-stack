# AoA Decisions MCP Access Plane

- Decision ID: ABYSS-STACK-D-0066
- Status: accepted
- Date: 2026-06-04
- Owner surface: `mcp/services/aoa-decisions-mcp/`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: MCP access plane, decision graph, generated/read-model
- Stack lanes: MCP services, decision lane, agent surface
- Mechanic parents: none
- Guard families: read-only access plane, decision graph freshness, MCP port confinement
- Posture: accepted decision-graph access-plane rationale

## Context

AoA repositories now carry repo-local `docs/decisions/` lanes with generated
indexes. Agents need a fast way to find decision rationale across the workspace,
follow source-surface links, and compare related records without loading every
repository decision lane into prompt context.

The source truth remains each repository's authored decision notes and local
generated indexes. A workspace graph can make retrieval cheaper, but it must
not become a second decision authority or a manual mirror.

## Options considered

1. Keep agents on direct repository reads only.
2. Generate a workspace decision graph but make agents invoke it by memory or
   manual shell commands.
3. Add a stack-owned MCP service that refreshes the graph automatically before
   reads and exposes compact decision packets to agents.

## Decision

Choose option 3.

Add `mcp/services/aoa-decisions-mcp/` as the stack-owned runnable MCP package
for the stable Codex server name `aoa_decisions`.

The service wraps the workspace decision graph builder, checks an input
fingerprint before every read, refreshes stale local graph output under ignored
`Logs/decision-graph/latest/`, and exposes read-only tools, resources, and
prompts for status, summary, search, repo packets, decision packets, and
explicit refresh.

The generated graph is a read model. It may accelerate lookup and route
selection, but decision creation, correction, supersession, and authority
changes still happen in the owning repository's `docs/decisions/` source lane
and its local validators.

## Rationale

This preserves the owner split. `abyss-stack` owns the runnable MCP adapter,
graph builder, and local cache. Each repository owns the decision records that
explain its own structure, route law, and future-facing choices.

Automatic refresh is required because a stale decision graph would mislead the
agent in exactly the path that is supposed to improve accuracy.

## Consequences

- Agents can ask `aoa_decisions` for compact decision context before reading
  source records.
- The graph refreshes automatically when the input fingerprint changes.
- The MCP remains stdio/read-only and writes only ignored local graph cache.
- Repo-local decision validators remain the write authority for records and
  indexes.
- Future write tools, remote exposure, scheduled daemon refresh, graph-backed
  acceptance, or graph-only decision creation require a new decision.

## Source surfaces

- `scripts/build_workspace_decision_graph.py`
- `tests/test_workspace_decision_graph.py`
- `mcp/AGENTS.md`
- `mcp/README.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-decisions-mcp/AGENTS.md`
- `mcp/services/aoa-decisions-mcp/DESIGN.md`
- `mcp/services/aoa-decisions-mcp/README.md`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/core.py`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/server.py`
- `mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py`
- `docs/validation/validation_lanes.json`
- `docs/validation/script_inventory.json`
- `docs/validation/validator_inventory.json`
- `docs/testing/test_inventory.json`

## Follow-up route

Wire the `aoa_decisions` server into the Codex-plane owner surface and expose
the agent-facing usage route through `aoa-skills`, with the MCP graph as the
first lookup path and repo-local decision files as source truth.
