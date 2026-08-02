# Stable and Next Compatibility Matrix

The authoritative machine-readable comparison is
`../protocol-compatibility-matrix.v1.json`.

## Current decision

Production stays on MCP `2025-11-25` with Codex `0.146.0`. The modern
`2026-07-28` registered read canary has now been exercised, but only through the exact
isolated prerelease Codex `0.147.0-alpha.4` binary with
`mcp_2026_07_28` explicitly enabled. This is a successful registered canary,
not a complete successful pair or a production cutover.

The separately named `aoa_kag_next_lab` contour used:

- a dedicated process and `127.0.0.1:5441` endpoint;
- a generated regular non-symlink `0600` bearer credential;
- an isolated `CODEX_HOME` and registration;
- Python MCP `2.0.0` and exact source-artifact digests;
- one exposed tool, `kag_discover`, with a deterministic schema digest.

The actual wire showed `server/discover`, protocol `2026-07-28`, no legacy
`initialize`, no `Mcp-Session-Id`, self-describing request envelopes, the
expected authenticated principal, and preserved trace context. A wrong bearer
received HTTP `401`. The server enforces a 16 KiB input bound and a 256 KiB
output bound; the oversized-input probe was rejected with MCP `-32602`.

Rollback stopped the Codex app-server and KAG lab server, closed the port, and
removed the lab registration, credential, and isolated `CODEX_HOME`. The
operator config digest remained byte-identical. Codex `0.146.0` then called
the existing `aoa_kag` registration successfully through the actual operator
config.

A separate direct Python MCP `2.0.0` cancellation probe did not preserve the
required lifecycle property. Local client cancellation occurred, but it did
not cancel the server dispatch, which completed afterward. P1-05 therefore
remains blocked even though the registered read call and rollback passed.

## Independent blockers

The current conformance checkout is exact commit
`81eb1c3edaed87d7fd585d7b80186da7a2960660`, newer than the still-public
`v0.1.16` release. Its Python `2.0.0` server SDK runner exposed twenty server
scenarios and passed 40 checks. The client fixture ran 33 scenarios, passed
372 checks, and failed these two new checks:

- `json-schema-2020-12-client-tool-found`;
- `json-schema-2020-12-client-echo-completed`.

The released Python fixture reports the scenario as unknown. The gap is kept
red rather than hidden in an expected-failure baseline. This current
conformance mismatch, failed cancellation propagation, and the absence of a
production-eligible modern Codex pair independently block core-read production
migration.

Python MCP `2.0.0` also does not implement the `2026-07-28` Tasks extension.
Tasks is therefore blocked separately and does not contaminate the core-read
gate. Candidate, internal-effect, and external-effect migration remain false
because the read pilot has no authority to advance them.

## Supporting behavior receipts

The earlier exact Python adapter receipts remain relevant and independent:

- stateless `server/discover` and self-describing requests;
- principal-bound opaque `requestState`, expiry, tamper rejection,
  cross-request replay denial, and key-retirement revocation;
- private TTL cache hits and expiry;
- `subscriptions/listen` addition/removal invalidation;
- stale-catalog inability to authorize a removed tool;
- explicit refresh after a disconnected listener.

These are bounded single-process read proofs. They do not prove multi-replica
fan-out, effectful replay safety, owner freshness, admission, or task benefit.

## Refresh workflow

1. Recheck official specification and SDK tags against exact current commits.
2. Recheck current conformance source, scenarios, and released fixture pair.
3. Re-run the isolated exact Codex pair whenever Codex, SDK, auth, schema, or
   transport changes.
4. Keep stable and lab names, processes, credentials, endpoints, and homes
   independent.
5. Re-run the stable operator-config canary after every lab rollback.
6. Update only receipt-backed gates and regenerate the status.
7. Do not perform production cutover until a production-eligible Codex pair
   has correct cancellation behavior and current conformance is green.

The matrix and current lab/rollback observations expire independently. The
generated status exposes their earliest expiry as `evidence_expires_at`.
