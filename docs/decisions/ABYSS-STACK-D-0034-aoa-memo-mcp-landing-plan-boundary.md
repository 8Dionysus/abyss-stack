# AoA Memo MCP Landing Plan Boundary

- Decision ID: ABYSS-STACK-D-0034
- Status: accepted
- Date: 2026-05-22
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-22
- Surface classes: MCP access plane, authority/boundary
- Stack lanes: MCP services, governed execution
- Mechanic parents: governed-execution
- Guard families: read-only access plane, source/runtime boundary
- Posture: accepted landing-plan boundary rationale

## Context

The first real reviewed memory landing used a stack-local `memo/` export as the
pilot source and landed durable memory through `aoa-memo`. Agents now need a
repeatable way to inspect which local exports are blocked, ready, or already
landed without giving the MCP service authority to write reviewed memory.

## Options considered

1. Keep landing entirely manual and make agents inspect export packets by hand.
2. Let `aoa-memo-mcp` write durable objects into `aoa-memo` directly.
3. Let `aoa-memo-mcp` list pending exports and build or dry-run landing plans,
   while the actual durable write remains an `aoa-memo` source change.

## Decision

Choose option 3.

`aoa-memo-mcp` exposes pending-export status and landing-plan helpers for known
local memo ports. It may run the `aoa-memo` landing script in dry-run mode, but
the reviewed memory object lands only through an explicit `aoa-memo` write,
generated read-model refresh, validation, and repository review.

Landing-plan readiness follows the same local source/evidence-ref posture as
the `aoa-memo` landing route: unresolved local refs block readiness before a
dry-run can claim that an export is ready to land. Symbolic refs such as
`repo:`, `web:`, or `operator:` remain route handles, not MCP-owned truth.

## Rationale

The service belongs to `abyss-stack` as an MCP access plane. It should make the
route visible from any agent entrypoint, but it should not become a second
memory authority. Keeping the durable write in `aoa-memo` preserves the owner
split while still giving agents a practical readiness path.

## Consequences

- Agents can see blocked, ready, and landed exports without manual packet
  archaeology.
- Missing local source/evidence refs surface as blocked readiness in MCP before
  an `aoa-memo` dry-run or source patch.
- The MCP can prepare commands and dry-run them, but cannot silently promote
  local memory into reviewed truth.
- Pilot local ports can be operated through one access-plane shape.
- Durable memory landing still requires `aoa-memo` validators and review.

## Source surfaces

- `mcp/services/aoa-memo-mcp/AGENTS.md`
- `mcp/services/aoa-memo-mcp/DESIGN.md`
- `mcp/services/aoa-memo-mcp/README.md`
- `mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/core.py`
- `mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/server.py`
- `mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/cli.py`
- `mcp/services/aoa-memo-mcp/tests/test_memo_mcp.py`
- `memo/AGENTS.md`
- `/srv/AbyssOS/aoa-memo/scripts/memory/land_reviewed_memo_intake.py`

## Follow-up route

If `aoa-memo-mcp` ever gains a write-mode integration, record a new decision in
`abyss-stack` and a matching authority decision in `aoa-memo` before enabling
it.
