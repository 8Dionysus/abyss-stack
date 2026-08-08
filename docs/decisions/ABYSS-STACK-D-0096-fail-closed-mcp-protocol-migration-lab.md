# Fail-Closed MCP Protocol Migration Lab

- Decision ID: ABYSS-STACK-D-0096
- Status: accepted
- Date: 2026-07-26
- Last evidence refresh: 2026-08-08
- Owner surface: `mcp/protocol-lab/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP protocol, compatibility lab, consumer admission
- Stack lanes: MCP services, organ access fabric, validation
- Mechanic parents: runtime-lifecycle
- Guard families: exact pin, fail closed, dual support, read-only canary, rollback
- Posture: accepted stable modern-lab proof with independent production admission

## Context

Final MCP `2026-07-28` changes core wire assumptions: the protocol session
handshake is removed, server discovery becomes explicit, application state
moves behind explicit handles, cache and trace metadata expand, and Tasks is a
separate extension. OS Abyss cannot infer compatibility from a date literal,
SDK type, schema listing, process start, or one unqualified client call.

The final specification is pinned at
`5f5440bb26a62e2cf3440b92da5a667efa03b267`. Python MCP `2.0.0` and
TypeScript client/server `2.0.0` are stable. Stable Codex `0.147.0` is the
current consumer, while the production registration remains on MCP
`2025-11-25`; an earlier isolated Python `2.0.0` exchange
fell back to `2025-06-18` and never sent `server/discover`.

Current conformance source at exact commit
`c321dd32035556e6769d3724a8ee97d87c3faaac` freezes requirements per
specification revision. Against the requirements frozen for `2026-07-28`, the
Python `2.0.0` client passed 372 scored checks in 32 scenarios and the server
passed 119 scored checks in 37 scenarios, with zero scored failures. Later
auth, JSON Schema, and Tasks scenarios still run for visibility; their
failures remain explicit but do not redefine a released revision
retroactively.

An exact stable Codex `0.147.0` isolated contour has passed the actual
registered modern read canary. With `mcp_2026_07_28` explicitly enabled, the separately named
and credentialed `aoa_kag_next_lab` used `server/discover`, MCP
`2026-07-28`, no legacy initialization, no MCP session header, and performed
one exact `kag_discover` call with principal and trace evidence. A wrong bearer
was rejected with HTTP `401`; an oversized request was rejected with MCP
`-32602` under explicit input/output bounds. The modern endpoint uses the SSE
response path so a disconnected Streamable HTTP request reaches the server
worker: the client request and server dispatch were both cancelled, and the
handler did not complete afterward. The Python `2.0.0` JSON-response shortcut
is not generalized as equivalent cancellation evidence.

Rollback removed only the lab app-server, MCP process, endpoint, credential,
registration, and isolated `CODEX_HOME`. The operator config remained
byte-identical, after which stable Codex `0.147.0` successfully called the
existing `aoa_kag` registration through the actual operator config. Because
the modern feature remains under development and the modern contour has not
received production admission, this passes the isolated lab pair but does not
authorize production cutover. Python MCP `2.0.0` also does
not implement the final Tasks extension. Production services intentionally
retain `mcp>=1.27.2,<2` and the `abyss-stack-mcp` exact `1.27.2` lock.

## Options considered

1. Update all organs when the final protocol tag appears.
2. Infer support from SDK/client source and switch the existing registration.
3. Pin a stable/next matrix, require exact pair receipts, retain stable support,
   and use one separately named, removable, read-only pilot.

## Decision

Choose option 3.

The production Codex-compatible wire remains MCP `2025-11-25`. The protocol
lab owns fourteen P1 gates over spec and SDK pins, Codex capabilities,
conformance, stable/next comparison, stateless behavior, explicit handles,
discovery, trace/cache behavior, Tasks, aliases, canary, dual support, and
rollback.

The first pilot is the compact read-only `aoa-kag` access plane. Its stable
registration remains `aoa_kag`. The modern lab uses `aoa_kag_next_lab` with
an independent process, endpoint, credential, runtime, exact consumer, and
Codex home. A stable pair with an explicitly enabled under-development feature
may pass the lab without acquiring production authority. Candidate and effect
organs are excluded, and protocol migration
cannot be combined with an owner-authority move.

The generated status reports separate:

- `core_read_migration_allowed`;
- `tasks_extension_allowed`;
- `candidate_migration_allowed`;
- `internal_effect_migration_allowed`;
- `external_effect_migration_allowed`.

P1-11 is Tasks-only and cannot block interpretation of the core-read gate. A
passed isolated pilot is reported separately from production eligibility.

## Rationale

Compatibility belongs to an exact client/server pair under an exact spec,
transport, credential, and source identity. Separating source pins from
runtime receipts makes freshness and missing proof visible. Keeping the stable
registration untouched makes rollback observable rather than aspirational.

KAG bounds blast radius and exercises discovery and owner-qualified read
behavior without durable memory, proof acceptance, source changes, or effects.

## Consequences

- P1-03 through P1-05, P1-13, and P1-14 pass on the stable modern canary,
  frozen-revision conformance, propagated cancellation, and rollback.
- P1-11 remains independently blocked on Tasks; the other thirteen gates pass.
- Stable Codex `0.147.0` is proven as an isolated modern lab consumer while
  its production registration remains on the legacy `2025-11-25` route.
- Production cutover requires an independent admission, deployment canary,
  registry refresh, observation window, and rollback for the production
  contour.
- Candidate, internal-effect, and external-effect migration remain false.
- A content-addressed watcher observes exact upstream releases, conformance
  main, Codex binary/features, local behavior sources, and evidence TTL. It may
  invoke only a removable configured lab suite and never advances production.

## Claim limits

This decision and its validators prove an exact stable modern Codex lab contour,
a separately credentialed registered read canary, fail-closed auth and input
bounds, lab removal, operator-config non-mutation, and stable-route recovery.
They do not prove production admission or cutover, multi-replica invalidation,
owner admission or acceptance, task
benefit, candidate safety, or any effect migration.

## Source surfaces

- `mcp/protocol-lab/`
- `mcp/services/aoa-kag-mcp/`
- `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
- `docs/decisions/ABYSS-STACK-D-0094-wave6-access-form-and-retirement-classification.md`

## Follow-up route

Let the watcher request a fresh exact lab whenever Codex, SDK, conformance,
auth, schema, source artifacts, transport, behavior, or evidence TTL changes.
Admit and deploy the production-shaped read contour only through its separate
registry, canary, observation, and rollback transaction. Wait for an exact
SDK/client extension pair before reopening Tasks. Candidate and effect
migration remain under later independent contracts.
