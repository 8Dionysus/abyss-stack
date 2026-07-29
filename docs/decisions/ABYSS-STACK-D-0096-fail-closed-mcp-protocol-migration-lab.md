# Fail-Closed MCP Protocol Migration Lab

- Decision ID: ABYSS-STACK-D-0096
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/protocol-lab/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP protocol, compatibility lab, consumer admission
- Stack lanes: MCP services, organ access fabric, validation
- Mechanic parents: runtime-lifecycle
- Guard families: exact pin, fail closed, dual support, read-only canary, rollback
- Posture: accepted post-final pair-evidence block

## Context

Final MCP `2026-07-28` changes core wire assumptions: the
protocol session handshake is removed, server discovery becomes explicit,
application state moves behind explicit handles, cache and trace metadata
expand, and Tasks remains a separately negotiated extension. OS Abyss cannot
infer compatibility from a date literal, SDK type, schema listing, successful
process start, or one client call.

On 2026-07-28 the final specification was published at exact commit
`5f5440bb26a62e2cf3440b92da5a667efa03b267`. Python MCP `2.0.0` and
TypeScript client/server `2.0.0` are stable. This closes publication gates but
not pair compatibility. An isolated stdio exchange between Codex `0.145.0` and
Python MCP `2.0.0` showed Codex offering and selecting `2025-06-18`, then
calling legacy list methods; it never sent `server/discover`. The current
next-protocol conformance package is still `0.2.0-alpha.10`. Against the exact
Python MCP `2.0.0` fixtures, its 2026 wire suite passes `114` server and `371`
client checks with zero failures, but that does not turn Codex into a modern
client. The isolated KAG next-protocol adapter subsequently passed the Abyss
pair, stateless, `server/discover`, explicit-handle, trace, and cache gates.
Those receipts prove only the exact isolated read adapter: the owner projection
was current, but owner freshness remained `source_unavailable`; no Codex
registration or consumer canary was enabled. Python MCP `2.0.0` explicitly
does not implement the final Tasks extension. Stack services intentionally
retain `mcp>=1.27.2,<2` and the `abyss-stack-mcp` exact lock `1.27.2`.

## Options considered

1. Update all organs when the final protocol tag appears.
2. Infer support from SDK/client source and switch the existing registration.
3. Pin a source-authored stable/next matrix, require pair-level receipts, keep
   stable support untouched, and admit one separately named read-only pilot
   only after every prerequisite passes.

## Decision

Choose option 3.

The current Codex-compatible wire remains MCP `2025-06-18`.
`mcp/protocol-lab/` owns fourteen
explicit P1 gates covering exact final spec and stable SDK pins, Codex
capabilities, official and Abyss conformance, stable/next comparison,
stateless behavior, explicit handles, `server/discover`, trace/cache behavior,
Tasks, aliases, a read-only canary, dual support, and rollback.

The first candidate is the compact read-only `aoa-kag` access plane. Its stable
registration remains `aoa_kag`. A future next-protocol lab uses the separate
disabled name `aoa_kag_next_lab`, an independent process and credential
contour, and rollback that removes only the lab registration. Candidate and
effect organs are excluded, and protocol migration cannot be combined with an
owner-authority move.

The generated status may permit migration only when every P1 gate and every
pair/runtime prerequisite passes. It always keeps effectful migration false.
Tasks has its own verdict and is not inferred from core protocol support.

## Rationale

Compatibility is a property of an exact client/server pair under an exact
specification and transport behavior. Separating authored pins from observed
receipts makes freshness and missing proof visible. Retaining the stable
registration makes rollback real and prevents a lab failure from removing the
known-good route.

Starting with KAG bounds blast radius and exercises real discovery and
read-result behavior without creating durable memory, accepting proof,
changing source, or emitting external effects.

## Consequences

- The current source verdict is blocked; P1-01, P1-02, P1-04 through P1-10,
  and P1-12 pass. P1-03, P1-11, P1-13, and P1-14 are blocked.
- Final publication and stable SDK availability are now proven, while Codex
  next-wire support is negatively resolved for version `0.145.0`.
- Official SDK conformance and the isolated Abyss adapter, handle, and cache
  receipts are proven without changing the stable Codex registration.
- Final publication alone cannot authorize migration.
- Every spec, SDK, conformance, Codex, transport, auth, or registration drift
  requires a refreshed observation.
- The future canary must record exact wire, schema, call, isolation, and
  rollback receipts.
- Organ migration beyond the read pilot requires later evidence and decisions.

## Claim limits

This decision and its green validators prove a deterministic, fail-closed
source gate, exact final/SDK pins, exact official SDK conformance, a bounded
legacy Codex wire observation, and isolated Abyss adapter, handle, and
single-process cache behavior. They do not prove modern Codex pair support, a
deployed or registered next server, a separately credentialed consumer canary,
multi-replica cache invalidation, owner freshness or acceptance, benefit, or
runtime rollback.

## Source surfaces

- `mcp/protocol-lab/`
- `mcp/services/aoa-kag-mcp/`
- `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
- `docs/decisions/ABYSS-STACK-D-0094-wave6-access-form-and-retirement-classification.md`

## Follow-up route

Refresh exact evidence when Codex changes or documents final-protocol support,
then repeat the isolated wire probe. Do not enable the isolated KAG lab
registration while Codex next-wire support or KAG owner freshness is blocked.
Wait for an exact SDK implementation before reopening the separate Tasks gate.
Only after those prerequisites pass, run a separately credentialed registered
consumer canary and exercise start/stop rollback without touching the stable
registration. Do not migrate an effectful organ in this phase.
