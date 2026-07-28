# Stable and Next Compatibility Matrix

The authoritative machine-readable comparison is
`../protocol-compatibility-matrix.v1.json`.

## Current decision

The production pair stays on MCP `2025-11-25`. The `2026-07-28-RC` line is
research-only until the final specification, a stable next SDK, actual Codex
pair evidence, both conformance layers, and a stable-preserving read canary
exist.

The important next-era behaviors are tested separately:

- removal of the protocol session handshake and request independence;
- explicit application-state handles, including isolation, expiry, replay,
  and revocation;
- `server/discover`;
- trace propagation and cache TTL/invalidation;
- wider JSON Schema behavior;
- Tasks as a distinct extension rather than implied core support.

## Refresh workflow

1. Recheck official specification tags and pin the exact final commit.
2. Recheck Python and TypeScript SDK releases and pin exact stable commits.
3. Recheck the official conformance release and pin its exact commit.
4. Record the actual Codex version and capture pair-level wire evidence.
5. Run official conformance against the exact server/client pair.
6. Run the Abyss checks for owner boundaries, handles, cache revocation,
   cancellation, credential isolation, and no authority merge.
7. Enable only the separately named read-only lab registration.
8. Run the `aoa-kag` read canary and exercise rollback without altering
   `aoa_kag`.
9. Update only gates supported by immutable receipts, then rebuild the status.

If any exact input drifts or the matrix expires, return to a blocked posture
until the observation is refreshed.
