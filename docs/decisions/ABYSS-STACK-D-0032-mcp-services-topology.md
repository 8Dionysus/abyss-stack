# MCP Services Topology

- Decision ID: ABYSS-STACK-D-0032
- Status: accepted
- Date: 2026-05-20
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-20
- Surface classes: MCP access plane, root/topology
- Stack lanes: MCP services
- Mechanic parents: none
- Guard families: MCP port confinement, read-only access plane
- Posture: accepted MCP service topology rationale

## Context

The first memory MCP access plane landed in `abyss-stack` because MCP is a
runtime-adjacent access layer, while durable memory authority belongs in
`aoa-memo`. The initial root-adjacent package path made ownership clear, but it
left service packages directly under the broad `mcp/` district.

As more MCP services become likely, the active topology needs a service
district that can hold runnable MCP packages without making the parent district
carry every service concern.

## Options considered

1. Keep `MCP/aoa-memo-mcp` as the active service path.
2. Rename only the parent district to `mcp/aoa-memo-mcp`.
3. Use `mcp/services/aoa-memo-mcp` as the canonical service package path.

## Decision

Use `mcp/services/aoa-memo-mcp` as the canonical path for the memory MCP service.

The parent `mcp/` district owns the access-plane family. The `mcp/services/`
district owns runnable MCP service packages. The service package owns
`aoa-memo-mcp` code, tests, prompts, resources, tools, and service-local docs.

## Rationale

The new path makes topology convex: parent district, service package district,
then concrete service. It gives future MCP services a clear place without
turning `mcp/` into a flat list of package internals.

Lowercase `mcp/` also follows the repository's active root naming style for
technical districts. The protocol name remains MCP in prose, while the path
uses the repository's route vocabulary.

## Consequences

- Agents now route through `mcp/AGENTS.md`, then `mcp/services/AGENTS.md`, then
  the service-local card.
- Validators check the service district and the concrete `aoa-memo-mcp`
  package under the new path.
- Historical memory candidates and receipts keep their event identity, while
  active evidence references point at the current source paths.
- The previous `MCP/` path is provenance for the first landing, not active
  topology.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/README.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-memo-mcp/AGENTS.md`
- `mcp/services/aoa-memo-mcp/DESIGN.md`
- `memo/AGENTS.md`
- `memo/README.md`
- `scripts/validate_stack.py`
- `scripts/validate_nested_agents.py`

## Follow-up route

Run:

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mcp/services/aoa-memo-mcp/tests -q
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

Use this path for future MCP service packages unless a later decision introduces
a different service topology.
