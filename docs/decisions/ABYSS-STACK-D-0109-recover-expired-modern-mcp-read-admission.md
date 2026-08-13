# Recover Expired Modern MCP Read Admission

- Decision ID: ABYSS-STACK-D-0109
- Status: accepted
- Date: 2026-08-10
- Owner surface: `scripts/aoa-refresh-modern-mcp-admission`

## Index Metadata

- Original date: 2026-08-10
- Surface classes: MCP access plane, runtime lifecycle, admission recovery
- Stack lanes: MCP services, runtime lifecycle, organ access fabric
- Mechanic parents: runtime-lifecycle
- Guard families: fail closed, exact identity, cold start, bootstrap handoff, rollback
- Posture: accepted bounded cold-start recovery

## Context

The modern read fleet correctly rejects an expired registry source and expired
contour evidence. After the host remains stopped beyond either currentness
window, production units therefore fail their preflight. The previous refresh
backstop could only probe already-running production processes, so it could not
produce the evidence required to make those same processes start. A full cold
start entered a fail-closed but self-unrecoverable cycle.

## Options considered

- Allow production units to start from expired registry or canary evidence.
- Extend or silently renew old admission claims across downtime.
- Keep cold recovery manual through the existing bootstrap procedure.
- Automate the already-proven bootstrap-to-production handoff while resetting
  expired registry claims and retaining every exact evidence gate.

## Decision

Choose the fourth option. The modern admission backstop may recover only the
fixed eleven admitted read organs. When their production units are unavailable
and registry-source or contour currentness is expired, it may start only the
already-defined manual bootstrap unit for each exact production pair. If the
registry source itself is expired, the controller first invokes the SDK's
expired-v2 rebase contract, which preserves owner shape and source identity but
resets every runtime, proof, acceptance, consumer, endpoint, freshness,
last-good, and admission claim to shadow.

The controller then captures distinct current and last-known-good signed
canaries bound to the bootstrap PIDs, publishes one temporary read admission,
and requires the derived preflight catalog to report exactly eleven eligible
and zero blocked contours. It stops all bootstrap units before starting the
fixed production set. Final publication requires a second distinct canary
family bound to the production PID/start identities and a rebuilt managed
catalog that matches those receipt IDs and reports exactly eleven eligible and
zero blocked contours. Bootstrap units remain manual and unenabled. A trap
stops bootstrap after every incomplete transaction and also stops a production
fleet started by the controller until final publication, catalog rebuild, and
registry validation all succeed.

The controller cannot accept organ, unit, endpoint, credential, tool, contour,
or policy inputs. It cannot touch candidate or internal-effect processes. The
existing registry CAS, deployment manifest, signer pin, protocol, owner-shaped
result contracts, proof, acceptance, rollback, and consumer compatibility
checks remain mandatory.

Canary collection may use a bounded worker pool across independent organs.
The last-known-good/current pair for one organ remains ordered, each worker
writes only that organ's addressed receipt paths, and publication remains a
barrier after the complete family succeeds. The default worker count is three,
one is exact sequential rollback, and the controller rejects counts outside
the literal eleven-organ fleet. This changes scheduling only; it does not
remove or weaken either bootstrap or production evidence family.

The same controller also repairs an incomplete production fleet while registry
and contour admission remain current. It reuses that admission only when the
registry deployment identity, all current production canaries, and the managed
catalog already match the exact current deployment. That fast path does not use
bootstrap or reset claims: it resets only the fixed production units' failed
state, starts the literal production set, then replaces the process-bound
canary and managed catalog family before completing. If time-current admission
is bound to a predecessor deployment, package, canary family, or catalog, the
controller instead rebuilds admission through the bounded bootstrap handoff;
repeated direct production starts would only replay a mandatory fail-closed
preflight rejection. The Codex credential launcher makes this controller a
synchronous pre-exec dependency whenever any of the eleven units or loopback
listeners is absent. A one-second boot timer starts the same transaction
eagerly; the launcher closes the remaining scheduling race.

## Rationale

Expired evidence must stay unusable, but fail-closed operation does not require
permanent unavailability. Resetting claims and replaying the exact proven
handoff establishes new evidence instead of laundering old timestamps. Keeping
the recovery set literal and requiring production receipts before completion
contains the new lifecycle effect to the same read fleet already admitted by
`ABYSS-STACK-D-0108`.

## Consequences

- A host cold start still runs every owner-shaped canary, but independent organ
  pairs are collected concurrently behind a bounded join; the admission
  oneshot retains its ten-minute fail-closed timeout.
- If production is unavailable while admission is still current and reusable
  for the exact deployment, recovery restarts only the exact production set and
  renews its process-bound evidence.
- If production is unavailable and time-current admission is bound to stale
  deployment or evidence identities, recovery uses the same bounded bootstrap
  handoff and replaces those identities before production start.
- Codex no longer starts an MCP-consuming session while the fixed fleet is
  absent. A bounded launcher failure is reported once before Codex execution
  instead of eleven transport failures retained for the whole session.
- Keeper and preflight watchers settle finite publication bursts without
  entering `unit-start-limit-hit`, and remain ordered behind the recovery
  transaction.
- An expired registry predecessor is preserved in the private run evidence,
  rebased only through the SDK contract, and replaced only after an unchanged
  predecessor digest check.
- Partial bootstrap, preflight, or production handoff leaves the fleet
  unavailable rather than widening authority.
- The fast path requires the managed catalog to match every current production
  receipt, so it repairs catalog drift instead of accepting registry currentness
  alone.
- This decision grants no candidate, Tasks, durable-write, internal-effect, or
  external-effect authority.

## Source surfaces

- `scripts/aoa-refresh-modern-mcp-admission`
- `systemd/user/abyss-mcp-modern-admission-refresh.service`
- `systemd/user/abyss-mcp-modern-admission-refresh.timer`
- `systemd/user/abyss-mcp-admission-keeper.service`
- `systemd/user/abyss-mcp-preflight-sweep.service`
- `mcp/services/_shared/codex_http_client.sh`
- `systemd/user/aoa-organ-mcp-read-bootstrap@.service`
- `systemd/user/abyss-stack-mcp-read-bootstrap.service`
- `mcp/services/abyss-stack-mcp/README.md`
- `mcp/services/abyss-stack-mcp/DESIGN.md`

## Follow-up route

Exercise one live expired cold-start rehearsal with an unchanged deployment,
prove zero remaining bootstrap identities and a real Codex consumer startup,
then keep the timer enabled as the recurrence backstop. Any expansion beyond
the exact read fleet requires a separate decision and threat model.
