# AoA Memo MCP Under Stack MCP

Status: accepted
Date: 2026-05-20

## Context

OS Abyss needs memory access from many working roots. `aoa-memo` already owns
reviewed memory truth and contracts, while `.aoa` owns raw session evidence.
The access layer needs MCP resources, tools, prompts, smoke tests, and local
candidate helpers without becoming a new memory authority.

## Options considered

1. Create a standalone `aoa-memory-mcp` repository for the first MCP server.
2. Place the first memory MCP under `abyss-stack/MCP/aoa-memo-mcp`.

## Decision

Place `aoa-memo-mcp` under `MCP/` in `abyss-stack` and keep local runtime memory
candidates under `memo/`.

`MCP/aoa-memo-mcp` is the stack-owned access plane. `aoa-memo` remains the
reviewed memory authority, `.aoa` remains the raw archive layer, and pilot
repositories keep local `memo/` ports for candidates, receipts, exports, and
local notes.

## Rationale

MCP is closer to runtime access than to memory doctrine. Keeping it under
`abyss-stack/MCP` makes the operational wiring discoverable beside other stack
adapters while preserving the source-of-truth hierarchy.

The separate-repository route would make a thin adapter look like a new owner
layer too early. The stack-local route keeps the first implementation small and
lets future extraction happen only if the MCP surface becomes independently
large enough to need its own release cadence.

## Consequences

- Agents get a single MCP route for memory briefs, local port status, candidate
  creation, validation, and session rehydration pointers.
- `abyss-stack` now has a root `MCP/` district and a local `memo/` port.
- Memory authority stays in `aoa-memo`; raw session evidence stays in `.aoa`.
- Future MCP servers can join the same district without expanding root prompts.

## Source surfaces

- `MCP/AGENTS.md`
- `MCP/README.md`
- `MCP/aoa-memo-mcp/AGENTS.md`
- `MCP/aoa-memo-mcp/DESIGN.md`
- `memo/AGENTS.md`
- `memo/README.md`

## Follow-up route

Run `python MCP/aoa-memo-mcp/scripts/validate_memo_mcp.py`,
`python scripts/validate_stack.py`, and `python scripts/validate_nested_agents.py`
after changing this access plane.
