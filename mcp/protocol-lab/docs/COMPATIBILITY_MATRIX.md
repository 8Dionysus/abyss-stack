# Stable and Next Compatibility Matrix

The authoritative machine-readable comparison is
`../protocol-compatibility-matrix.v1.json`.

## Current decision

The production Codex/Abyss pair stays on MCP `2025-11-25`; a minimized
source fixture binds its schema and direct-call observation to the digest of
the private receipt without retaining credentials or raw output. That call is
not treated as the next-protocol canary. Final MCP `2026-07-28`,
Python MCP `2.0.0`, and TypeScript client/server `2.0.0` are exact-pinned, but
this release readiness does not form a usable Codex pair. An isolated stdio
probe against Python MCP `2.0.0` showed Codex `0.146.0` sending `initialize`
and falling back to `2025-06-18`; it did not send `server/discover`. That
fallback does not redefine the production wire. Migration therefore remains
blocked until a new Codex
observation, Abyss pair-conformance, and a stable-preserving read canary
exist. The exact Python MCP `2.0.0` server and client fixtures pass the pinned
tested `0.2.0-alpha.10` package at wire `2026-07-28` (`114` and `371`
successful checks, zero failures); that receipt is deliberately SDK-scoped.
The latest public conformance release is still `v0.1.16` from 2026-03-27 and
does not provide observed final-protocol scenarios, so it is recorded
separately rather than being confused with the tested prerelease package.
Separately, an isolated Python MCP `2.0.0` KAG adapter pair proved
`server/discover`, self-describing stateless requests across two clients,
private TTL cache use, trace propagation, and fail-closed effect/legacy
denials. It did not alter stable Codex configuration. This advances the Abyss
adapter, stateless, and discovery gates, but that first receipt alone did not
prove explicit handles or full cache invalidation/revocation. The KAG exact
projection was current while owner freshness reported `source_unavailable`,
which is preserved as a canary blocker.
The same isolated owner then passed the explicit `requestState` handle gate
over stateless HTTP with per-request bearer verification: a handle completed
for its original principal and request, expired deterministically, failed for
another subject of the same OAuth client, failed on different arguments,
failed after tampering, and failed after its signing key was retired across a
server restart. Same-request replay returned the identical read result and is
recorded as read-only/idempotent behavior, not a policy for effects.
The catalog cache gate then passed independently: one private `tools/list`
response was reused within 30 seconds and refetched exactly at expiry;
subscription events invalidated additions and removals before the next list;
events published without a listener were not replayed; an old warm listing
could still mention a removed lab tool but the server refused its call; and an
explicit refresh replaced that stale entry. This is a single-process bus
proof, not multi-replica fan-out.

Together these isolated receipts pass the adapter, stateless, handle,
discovery, trace, and cache gates. They do not pass the Codex consumer gate,
registered canary, owner-freshness gate, dual-registration exercise, or
runtime rollback. Those latter gates remain blocked, not merely assumed from
source-defined rollback law.

The important next-era behaviors are tested separately:

- removal of the protocol session handshake and request independence;
- explicit application-state handles, including isolation, expiry, replay,
  and revocation;
- `server/discover`;
- trace propagation and cache TTL/invalidation;
- wider JSON Schema behavior;
- Tasks as a distinct extension rather than implied core support.

Python MCP `2.0.0` explicitly does not implement the final Tasks extension,
so the Tasks gate is blocked on this exact SDK line rather than merely
unobserved.

## Refresh workflow

1. Recheck official specification and SDK tags against their exact current
   commits.
2. Recheck the official conformance package and pin its exact package commit.
3. Record the actual Codex version and repeat the isolated pair-level wire
   probe.
4. Run official conformance against the exact server/client pair.
5. Run the Abyss checks for owner boundaries, handles, cache revocation,
   cancellation, credential isolation, and no authority merge.
6. Enable only the separately named read-only lab registration.
7. Run the `aoa-kag` read canary and exercise rollback without altering
   `aoa_kag`.
8. Update only gates supported by immutable receipts, then rebuild the status.

If any exact input drifts, the matrix expires, or the production-pair receipt
expires, validation fails and the lab returns to a blocked posture until the
observation is refreshed. The generated status exposes the earliest of those
source expiries as `evidence_expires_at`.
