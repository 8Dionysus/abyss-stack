# AoA KAG MCP Access Plane

- Decision ID: ABYSS-STACK-D-0075
- Status: superseded
- Superseded by: `ABYSS-STACK-D-0079-kag-query-application-port.md`
- Date: 2026-06-28
- Owner surface: `mcp/services/aoa-kag-mcp/`

## Index Metadata

- Original date: 2026-06-28
- Surface classes: MCP access plane, KAG provider map, generated/read-model
- Stack lanes: MCP services, validation lane, agent surface
- Mechanic parents: federation-seams
- Guard families: read-only access plane, source-return route, provider freshness, MCP port confinement
- Posture: superseded provider-map-only access-plane rationale

## Context

`aoa-kag` now owns a complete direct-repo provider map for OS Abyss KAG homes.
Agents need a compact way to inspect provider readiness, source-return handles,
freshness receipts, registry slices, and provider records without loading the
whole workspace or asking a runtime service to infer source topology.

The source truth remains split by owner: `aoa-kag` owns schemas, readiness,
generated provider maps, and KAG validation; each source repository owns its
repo-local `kag/` provider packet and owner-return routes; `abyss-stack` owns
runnable MCP access planes.

## Options considered

1. Keep KAG access as direct repository reads only.
2. Let `aoa-kag-mcp` crawl repository roots and infer provider status at read time.
3. Add a stack-owned read-only MCP package that serves the generated provider
   map and repo-local provider records through explicit tools, resources, and
   prompts.

## Decision

Choose option 3.

Add `mcp/services/aoa-kag-mcp/` as the stack-owned runnable MCP package for
KAG provider-map access. The service reads
`aoa-kag/generated/local_kag_provider_map.min.json`,
`aoa-kag/manifests/local_kag_readiness.json`, and repo-local `kag/` provider
records through source-return routes. It exposes read-only tools for provider
status, lookup, freshness, source-return lookup, registry slices, composition
slices, and validation status; resources for provider maps, OS-surface
readiness, manifests, and record-class packets; and prompts for bounded
provider queries, source-return summaries, relation previews, and runtime
handoff briefs.

The service may report freshness handles from provider receipts. It does not
mutate provider homes, generate embeddings, write graph/vector/runtime state,
run owner validators as hidden side effects, or redefine KAG source meaning.

## Rationale

This keeps access fast while preserving authority. MCP can reduce context load
for agents, but KAG topology remains generated and validated by `aoa-kag`, with
record meaning returned to each source repository. `abyss-stack` contributes
only the runnable adapter, package tests, route cards, and validation-lane
integration.

The explicit resource/tool/prompt split matches the MCP service model and keeps
future graph, vector, DAG, and agentic retrieval layers attachable without
folding mutable runtime state into source Git.

## Consequences

- Agents can inspect the OS Abyss KAG provider map through one bounded MCP
  route.
- `aoa-kag-mcp` is part of the blocking `mcp-services` validation lane.
- Source-structure, nested AGENTS, script inventory, validator inventory, and
  test inventory now cover the service package.
- Freshness reads remain receipt-backed and non-mutating.
- Future write tools, validator execution, graph materialization,
  vector-store reads, non-stdio exposure, generated-map mutation, or source
  owner promotion require a new decision.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-kag-mcp/AGENTS.md`
- `mcp/services/aoa-kag-mcp/DESIGN.md`
- `mcp/services/aoa-kag-mcp/README.md`
- `mcp/services/aoa-kag-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-kag-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-kag-mcp/src/aoa_kag_mcp/core.py`
- `mcp/services/aoa-kag-mcp/src/aoa_kag_mcp/server.py`
- `mcp/services/aoa-kag-mcp/src/aoa_kag_mcp/cli.py`
- `mcp/services/aoa-kag-mcp/scripts/validate_kag_mcp.py`
- `mcp/services/aoa-kag-mcp/tests/test_kag_mcp.py`
- `docs/validation/validation_lanes.json`
- `docs/validation/script_inventory.json`
- `docs/validation/validator_inventory.json`
- `docs/testing/test_inventory.json`
- `scripts/validators/source_structure.py`
- `scripts/validate_nested_agents.py`
- `aoa-kag:generated/local_kag_provider_map.min.json`
- `aoa-kag:manifests/local_kag_readiness.json`
- `aoa-kag:kag/LOCAL_SUBTREE_PROTOCOL.md`
- `aoa-kag:docs/decisions/AOA-KAG-D-0012-direct-repo-provider-completion.md`

## Follow-up route

`ABYSS-STACK-D-0079` retains this decision's owner split and replaces its
provider-map-only interface with the runtime-neutral KAG query application
port.
