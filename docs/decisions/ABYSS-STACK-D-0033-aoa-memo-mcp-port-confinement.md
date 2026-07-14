# AoA Memo MCP Port Confinement

- Decision ID: ABYSS-STACK-D-0033
- Status: accepted
- Date: 2026-05-21
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-21
- Surface classes: MCP access plane, validation guard
- Stack lanes: MCP services
- Mechanic parents: none
- Guard families: MCP port confinement, read-only access plane
- Posture: accepted MCP confinement rationale

## Context

`aoa-memo-mcp` helps agents read memory briefs, create local candidates, build
port indexes, prepare reviewed-intake exports, and write local receipts. The
first layer proved the route, but packet paths and local intake checks needed a
clearer boundary so the service could not validate or forward files outside a
known local `memo/` port.

## Options considered

1. Keep path handling permissive and rely on caller discipline.
2. Allow absolute packet paths for convenience while documenting the risk.
3. Confine candidate, export, and receipt packet handling to known local
   `memo/` ports and validate packets against `aoa-memo` schemas.

## Decision

Confine `aoa-memo-mcp` packet operations to known local `memo/` ports.

Candidate, export, receipt, port, and port-index packets are validated against
`aoa-memo/schemas/memory-ports/`. Packet references for candidates, exports,
and receipts are local port refs, not arbitrary absolute paths. The
`aoa_memo_review_intake` tool remains a compatibility name, but its result is a
local forwarding check receipt rather than durable memory review.

## Rationale

The MCP service is an access plane. It should make the memory route easy to
use, but it should not expand its authority by accepting out-of-port packets or
by producing receipts that sound like central review. Schema-backed validation
lets `aoa-memo` keep ownership of packet shape while `abyss-stack` owns the
runnable service.

## Consequences

- Local packet operations are bounded to the pilot memory ports.
- Invalid vocabulary and schema failures stop candidate creation before files
  are written.
- Forwarding receipts use `checked_by`, not `reviewed_by`.
- Durable reviewed memory still lands only through an `aoa-memo` source change
  and review.
- Absolute packet-path convenience is traded for a clearer access-plane
  boundary; evidence refs may still point at source evidence as packet content.

## Source surfaces

- `mcp/services/aoa-memo-mcp/AGENTS.md`
- `mcp/services/aoa-memo-mcp/DESIGN.md`
- `mcp/services/aoa-memo-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-memo-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/core.py`
- `mcp/services/aoa-memo-mcp/tests/test_memo_mcp.py`
- `memo/PORT.yaml`
- `/srv/AbyssOS/aoa-memo/schemas/memory-ports/`

## Follow-up route

Use the service-local `AGENTS.md` release route after boundary changes. It owns
the current command and failure route.

When a second MCP service lands, add a parent `mcp/` service registry instead
of embedding registry behavior in `aoa-memo-mcp`.
