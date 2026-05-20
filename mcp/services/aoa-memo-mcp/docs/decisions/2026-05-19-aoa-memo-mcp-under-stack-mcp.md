# Decision: Place `aoa-memo-mcp` Under `abyss-stack/MCP`

Status: superseded
Superseded by: `docs/decisions/2026-05-20-mcp-services-topology.md`
Date: 2026-05-19

## Context

`aoa-memo` now owns reviewed memory operation contracts, while `.aoa` owns raw
session archive evidence. Agents still need a live route that works from any
repository without flattening memory into prompts or copying central files into
each root.

## Options considered

1. Create a separate `aoa-memory-mcp` repository.
2. Place the first memory MCP under `abyss-stack/MCP/aoa-memo-mcp`.

## Decision

Place `aoa-memo-mcp` under `abyss-stack/MCP/`.

The server owns MCP resources, tools, prompts, smoke tests, and local candidate
helpers. It exposes memory access, but it does not promote memory, replace raw
evidence, or become durable truth.

## Rationale

MCP is an access plane and runtime-adjacent adapter, so its first implementation
belongs with `abyss-stack` rather than beside `aoa-memo` as a new authority.
This keeps the operational route close to runtime wiring while keeping reviewed
memory contracts in `aoa-memo`.

## Consequences

- Agents get one addressable memory route across pilot roots.
- Local `memo/` ports can stay small and repo-owned.
- `aoa-memo` remains central authority for durable memory.
- `.aoa` remains the evidence archive.
- Future clients can wire the MCP server by stable name without importing
  `aoa-memo` internals into every agent prompt.

## Source surfaces

- `MCP/AGENTS.md`
- `MCP/aoa-memo-mcp/AGENTS.md`
- `MCP/aoa-memo-mcp/DESIGN.md`
- `memo/AGENTS.md`

## Follow-up route

For the current active path, use `mcp/services/aoa-memo-mcp/` and the stack
release gate when changing the access plane.
