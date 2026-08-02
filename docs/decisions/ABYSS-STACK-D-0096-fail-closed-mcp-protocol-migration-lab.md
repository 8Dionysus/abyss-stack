# Fail-Closed MCP Protocol Migration Lab

- Decision ID: ABYSS-STACK-D-0096
- Status: accepted
- Date: 2026-07-26
- Last evidence refresh: 2026-08-01
- Owner surface: `mcp/protocol-lab/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP protocol, compatibility lab, consumer admission
- Stack lanes: MCP services, organ access fabric, validation
- Mechanic parents: runtime-lifecycle
- Guard families: exact pin, fail closed, dual support, read-only canary, rollback
- Posture: accepted modern-lab proof with production cutover blocked

## Context

Final MCP `2026-07-28` changes core wire assumptions: the protocol session
handshake is removed, server discovery becomes explicit, application state
moves behind explicit handles, cache and trace metadata expand, and Tasks is a
separate extension. OS Abyss cannot infer compatibility from a date literal,
SDK type, schema listing, process start, or one unqualified client call.

The final specification is pinned at
`5f5440bb26a62e2cf3440b92da5a667efa03b267`. Python MCP `2.0.0` and
TypeScript client/server `2.0.0` are stable. Production Codex `0.146.0`
remains on MCP `2025-11-25`; its earlier isolated Python `2.0.0` exchange
fell back to `2025-06-18` and never sent `server/discover`.

Current conformance source at exact commit
`81eb1c3edaed87d7fd585d7b80186da7a2960660` changes the former green SDK
observation. The Python `2.0.0` server fixture passed 40 checks in the twenty
scenarios exposed by its SDK runner. The client fixture passed 372 checks and
failed two because it does not recognize the newly added
`json-schema-2020-12-preservation` scenario. The mismatch is a real blocker
and is not hidden in an expected-failure baseline.

An exact Codex `0.147.0-alpha.4` isolated contour has passed the actual
registered modern read canary. With `mcp_2026_07_28` explicitly enabled, the separately named
and credentialed `aoa_kag_next_lab` used `server/discover`, MCP
`2026-07-28`, no legacy initialization, no MCP session header, and performed
one exact `kag_discover` call with principal and trace evidence. A wrong bearer
was rejected with HTTP `401`; an oversized request was rejected with MCP
`-32602` under explicit input/output bounds. A separate direct Python MCP
`2.0.0` cancellation probe then found that local client cancellation did not
stop server dispatch: the client request was cancelled, but the server handler
completed afterward. That is a failed pair property, not a passed canary fact.

Rollback removed only the lab app-server, MCP process, endpoint, credential,
registration, and isolated `CODEX_HOME`. The operator config remained
byte-identical, after which Codex `0.146.0` successfully called the existing
`aoa_kag` registration through the actual operator config. Because the modern
consumer is a prerelease, current conformance is red, and cancellation does
not propagate, this closes the registered canary and rollback experiment but
does not pass the complete lab pair or authorize production cutover. Python MCP `2.0.0` also does
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
Codex home. A prerelease pair may pass the lab without acquiring production
authority. Candidate and effect organs are excluded, and protocol migration
cannot be combined with an owner-authority move.

The generated status reports separate:

- `core_read_migration_allowed`;
- `tasks_extension_allowed`;
- `candidate_migration_allowed`;
- `internal_effect_migration_allowed`;
- `external_effect_migration_allowed`.

P1-11 is Tasks-only and cannot block interpretation of the core-read gate. A
passed prerelease pilot is reported separately from production eligibility.

## Rationale

Compatibility belongs to an exact client/server pair under an exact spec,
transport, credential, and source identity. Separating source pins from
runtime receipts makes freshness and missing proof visible. Keeping the stable
registration untouched makes rollback observable rather than aspirational.

KAG bounds blast radius and exercises discovery and owner-qualified read
behavior without durable memory, proof acceptance, source changes, or effects.

## Consequences

- P1-03, P1-13, and P1-14 now pass on the actual prerelease canary and rollback.
- P1-04 remains blocked on the current conformance fixture mismatch.
- P1-05 remains blocked because client cancellation did not stop server
  dispatch.
- P1-11 remains independently blocked on Tasks; the other eleven gates pass.
- Codex `0.146.0` remains the legacy production consumer; Codex
  `0.147.0-alpha.4` is proven only as an isolated modern lab consumer.
- Production cutover requires both a production-eligible modern Codex pair and
  green current conformance.
- Candidate, internal-effect, and external-effect migration remain false.
- Every spec, SDK, conformance, Codex, transport, auth, source-artifact, or
  registration drift requires a refreshed observation.

## Claim limits

This decision and its validators prove an exact prerelease modern Codex contour,
a separately credentialed registered read canary, fail-closed auth and input
bounds, lab removal, operator-config non-mutation, and stable-route recovery.
They do not prove a production-eligible modern Codex pair, green current
conformance, propagated cancellation, multi-replica invalidation, owner admission or acceptance, task
benefit, candidate safety, or any effect migration.

## Source surfaces

- `mcp/protocol-lab/`
- `mcp/services/aoa-kag-mcp/`
- `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
- `docs/decisions/ABYSS-STACK-D-0094-wave6-access-form-and-retirement-classification.md`

## Follow-up route

Refresh the exact lab whenever Codex, SDK, auth, schema, source artifacts, or
transport changes. Repair or refresh the current conformance fixture pair,
prove cancellation propagation, and wait for a production-eligible Codex
modern pair before reopening core-read production cutover. Wait for an exact SDK implementation before reopening
Tasks. Candidate and effect migration remain under later independent
contracts.
