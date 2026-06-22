# AoA 4PDA Connector MCP Access Plane

- Decision ID: ABYSS-STACK-D-0072
- Status: accepted
- Date: 2026-06-21
- Owner surface: `mcp/services/aoa-4pda-connector-mcp/`

## Index Metadata

- Original date: 2026-06-21
- Surface classes: MCP access plane, source/runtime boundary, federation/read-model
- Stack lanes: MCP services, federation seams
- Mechanic parents: federation-seams
- Guard families: MCP port confinement, read-only access plane, source/runtime boundary, source-structure
- Posture: accepted 4PDA connector MCP access-plane rationale

## Context

`aoa-4pda-connector` now produces local answer packets with `agent_answer`,
`evidence_chain`, `nuance_report`, `answer_report`, source URLs, freshness, and
`network_touched=false`. Agents need an MCP route to use those packets without
manually rediscovering the connector CLI and storage roots.

The connector repository is public and portable. It owns the method, source
policy, CLI, schemas, answer packet behavior, and portable MCP rollout
contract. `abyss-stack` owns runtime MCP services, stdio exposure, validation
lanes, and deployment posture. Mixing those owners would either make the public
connector own stack runtime, or make stack code appear to own source-specific
4PDA truth.

## Options considered

1. Keep 4PDA connector access as direct CLI calls only.
2. Put the MCP implementation in `aoa-4pda-connector`.
3. Add a distinct `aoa-4pda-connector-mcp` package in `abyss-stack` that wraps
   the connector CLI read-only.

## Decision

Choose option 3.

Add `mcp/services/aoa-4pda-connector-mcp/` as the stack-owned runtime MCP
service package for 4PDA connector evidence. The package wraps `aoa-4pda`
without a shell, parses JSON stdout, and exposes status, source-route,
graph/hybrid query, and answer tools/resources.

The first surface is read-only and local-only. It does not expose crawl,
refresh-build, materialize, reindex, seed-edit, approval, or write tools. It
must preserve source answer fields including `agent_answer`, `evidence_chain`,
`nuance_report`, `answer_report`, and `network_touched=false`.

## Rationale

A distinct MCP service keeps the owner split visible. Agents can use local 4PDA
evidence through one stable runtime access plane, while source authority stays
with the public connector repository and generated data stays in configured
connector storage roots outside Git.

The read-only first slice is enough for agent answer/review work and avoids
turning MCP into a crawler, seed editor, or build orchestrator before the
connector's source-side contracts ask for that expansion.

## Consequences

- Agents get a stack-native MCP route for local 4PDA answers with citations,
  evidence chains, nuance, and freshness.
- The service depends on the connector CLI and local storage being configured;
  missing connector state is reported by status packets rather than repaired by
  MCP.
- Future crawl, refresh-build, reindex, seed-edit, write, non-stdio exposure,
  or network tools require a separate decision and source-side contract update.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-4pda-connector-mcp/AGENTS.md`
- `mcp/services/aoa-4pda-connector-mcp/DESIGN.md`
- `mcp/services/aoa-4pda-connector-mcp/README.md`
- `mcp/services/aoa-4pda-connector-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-4pda-connector-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-4pda-connector-mcp/src/aoa_4pda_connector_mcp/core.py`
- `mcp/services/aoa-4pda-connector-mcp/src/aoa_4pda_connector_mcp/server.py`
- `mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py`
- `mcp/services/aoa-4pda-connector-mcp/tests/test_4pda_connector_mcp.py`
- `aoa-4pda-connector:docs/MCP_ROLLOUT.md`
- `aoa-4pda-connector:docs/RUNTIME_CONTRACT.md`

## Follow-up route

Run:

```bash
python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q
python scripts/generate_decision_indexes.py --check
python scripts/validate_decision_records.py
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

For local OS Abyss smoke, point `AOA_4PDA_CONNECTOR_REPO` at the connector
checkout and run an answer against an existing materialized connector run.
