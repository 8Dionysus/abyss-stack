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
- Posture: accepted pre-final migration block

## Context

The MCP `2026-07-28` release candidate changes core wire assumptions: the
protocol session handshake is removed, server discovery becomes explicit,
application state moves behind explicit handles, cache and trace metadata
expand, and Tasks remains a separately negotiated extension. OS Abyss cannot
infer compatibility from a date literal, SDK type, schema listing, successful
process start, or one client call.

As observed on 2026-07-26, the final specification is not published. The exact
next Python and TypeScript SDK lines are prereleases. Local Codex 0.145.0
contains next-version and Tasks literals, but also stable session lifecycle
paths; no actual `2026-07-28` exchange or `server/discover` receipt exists.
The stable Python SDK is 1.28.1 while stack services retain the compatible
`mcp>=1.27.2,<2` constraint and `abyss-stack-mcp` exact lock 1.27.2.

## Options considered

1. Update all organs when the final protocol tag appears.
2. Infer support from SDK/client source and switch the existing registration.
3. Pin a source-authored stable/next matrix, require pair-level receipts, keep
   stable support untouched, and admit one separately named read-only pilot
   only after every prerequisite passes.

## Decision

Choose option 3.

Production remains on MCP `2025-11-25`. `mcp/protocol-lab/` owns fourteen
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

- The current source verdict is blocked; only P1-06 and P1-12 pass.
- Final publication alone cannot authorize migration.
- Every spec, SDK, conformance, Codex, transport, auth, or registration drift
  requires a refreshed observation.
- The future canary must record exact wire, schema, call, isolation, and
  rollback receipts.
- Organ migration beyond the read pilot requires later evidence and decisions.

## Claim limits

This decision and its green validators prove a deterministic, fail-closed
source gate. They do not prove final publication, stable next SDK readiness,
Codex pair support, official or Abyss conformance, a deployed next server,
consumer registration, live canary, benefit, or rollback.

## Source surfaces

- `mcp/protocol-lab/`
- `mcp/services/aoa-kag-mcp/`
- `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
- `docs/decisions/ABYSS-STACK-D-0094-wave6-access-form-and-retirement-classification.md`

## Follow-up route

Refresh exact evidence after the final release and stable SDK/client support
exist. Run official conformance and the Abyss pair suite before enabling the
isolated KAG lab registration. Do not touch the stable registration and do not
migrate an effectful organ in this phase.
