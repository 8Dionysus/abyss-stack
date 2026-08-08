# Stable and Next Compatibility Matrix

The authoritative machine-readable comparison is
`../protocol-compatibility-matrix.v1.json`.

## Current decision

Production stays on MCP `2025-11-25`. Stable Codex `0.147.0` is current, but
its production `aoa_kag` registration has not been moved. With
`mcp_2026_07_28` enabled only in an isolated `CODEX_HOME`, the same exact
binary passed the separately named `aoa_kag_next_lab` contour on the real
`2026-07-28` wire. That is stable-client lab compatibility, not production
admission.

The removable contour used an independent process, loopback endpoint,
generated mode `0600` credential, registration, Codex home, Python MCP `2.0.0`
runtime, and exact source-artifact digests. The wire showed
`server/discover`, self-describing requests, no legacy `initialize`, no
`Mcp-Session-Id`, the expected authenticated principal, trace propagation, one
exact KAG tool/schema inventory, wrong-bearer `401`, explicit input/output
bounds, and oversized-input denial.

The modern server uses the SSE response path. A client disconnect cancelled
the client request and the actual server dispatch, and the worker did not
complete afterward. This receipt does not generalize to the Python `2.0.0`
JSON-response shortcut, whose handler path does not watch disconnects.

Rollback removed the lab app-server, MCP process, port, credential,
registration, and isolated Codex home. The operator config remained
byte-identical, after which stable Codex `0.147.0` called the unchanged
production `aoa_kag` registration successfully.

## Frozen conformance

Official conformance commit
`c321dd32035556e6769d3724a8ee97d87c3faaac` adds requirements frozen per
specification revision. Against `--requirements 2026-07-28`, Python MCP
`2.0.0` passed all 372 scored client checks across 32 scenarios and all 119
scored server checks across 37 scenarios. There is no expected-failure
baseline.

Seven later client scenarios and thirteen later server scenarios also ran for
visibility. Their auth, JSON Schema, and Tasks failures remain explicit and
unscored because they were added after the frozen release requirements. This
classification removes the former false retroactive blocker without hiding
future work.

## Independent gates

P1-01 through P1-10 and P1-12 through P1-14 pass. P1-11 remains blocked
independently:

- Python MCP `2.0.0` does not implement the Tasks extension;
- stable Codex `0.147.0` did not advertise
  `_meta.io.modelcontextprotocol/clientCapabilities.extensions["io.modelcontextprotocol/tasks"]`
  on the real request wire;
- an owner-bounded replacement adapter and its own compatibility proof are
  still required.

The isolated read-only pilot is allowed and complete. Production core-read
migration remains false until the exact production contour receives its own
admission transaction, deployment canary, registry refresh, observation
window, and rollback. Candidate, internal-effect, and external-effect
contours cannot inherit the read result.

## Supporting behavior receipts

The exact isolated receipts separately prove:

- stateless `server/discover` and self-describing requests;
- principal-bound opaque `requestState`, expiry, tamper rejection,
  cross-request replay denial, and key-retirement revocation;
- private TTL cache hits and expiry;
- `subscriptions/listen` addition/removal invalidation;
- stale-catalog inability to authorize a removed tool;
- explicit refresh after a disconnected listener.

These are bounded single-process read proofs. They do not prove multi-replica
fan-out, effectful replay safety, owner acceptance, production admission, or
Tasks benefit.

## Automated refresh workflow

`../protocol-watch-plan.v1.json` and `../scripts/protocol_watcher.py` observe:

1. exact Codex bytes, version, and feature output;
2. latest published Codex, MCP specification, and Python/TypeScript SDK
   identities;
3. current conformance `main` commit;
4. local auth, cancellation, cache, handle/MRTR, and extension behavior source;
5. the matrix/status bytes and earliest evidence expiry.

An identity change, absent successful baseline, or approaching TTL requests a
new isolated lab. Required network or local input failure blocks the run. A
private mode `0600` runtime plan may execute multiple exact argv steps inside a
unique run root; no shell text is evaluated. The watcher hashes required
receipts, prevents secret publication, compares protected production files
before and after, and advances its baseline only after a fully successful
suite.

The event-driven path unit handles local changes. The hourly timer polls
upstream identities and acts as a TTL backstop. Neither unit changes production
automatically. Every successful lab still requires a separate owner/runtime
admission before any production cutover.
