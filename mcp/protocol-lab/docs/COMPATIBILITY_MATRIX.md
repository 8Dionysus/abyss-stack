# Stable and Next Compatibility Matrix

The authoritative machine-readable comparison is
`../protocol-compatibility-matrix.v1.json`.

## Current decision

The source transition is now pinned to Python MCP `2.1.1` with the paired
`mcp-types==2.1.1`; the production paragraphs below intentionally preserve the
previous `2.0.0` deployment receipt as historical evidence until a fresh
owner-approved deployment receipt exists. They must not be read as proof that
the deployed fleet has already moved to 2.1.1.

Production uses MCP `2026-07-28` for the eleven admitted OS Abyss organ read
registrations. Each deployment-bound listener is still evidenced on exact
Python MCP `2.0.0`, advertises only the modern wire, rejects wrong bearer and
legacy initialization before session creation, and is bound to a production
process identity rather than a bootstrap unit. The source candidate now pins
Python MCP `2.1.1`, but no production cutover is claimed from source-only proof.
OS Abyss Codex `0.147.0-abyss.2` selects this wire only for the explicit
organ allow-list; upstream Codex and unrelated external MCP owners are separate
compatibility rows.

The isolated `aoa_kag_next_lab` contour is now refreshed as a removable MCP
`2.1.1` candidate proof. The older `2.0.0` lab and post-rollback receipts remain
historical evidence and no longer stand in for the candidate deployment proof.

The removable contour used an independent process, loopback endpoint,
generated mode `0600` credential, registration, Codex home, Python MCP `2.1.1`
runtime, and exact source-artifact digests. The wire showed
`server/discover`, self-describing requests, no legacy `initialize`, no
`Mcp-Session-Id`, the expected authenticated principal, trace propagation, one
exact KAG tool/schema inventory, wrong-bearer `401`, explicit input/output
bounds, and oversized-input denial.

The modern server uses the SSE response path. A client disconnect cancelled
the client request and the actual server dispatch, and the worker did not
complete afterward. This receipt does not generalize to the Python `2.1.1`
JSON-response shortcut, whose handler path does not watch disconnects.

Rollback removed the candidate lab app-server, MCP process, port, credential,
registration, and isolated Codex home. The operator config remained
byte-identical. The separate stable post-rollback call is retained as
historical deployment-bound MCP `2.0.0` evidence and does not authorize a
candidate cutover.

## Frozen conformance

Official conformance commit
`c321dd32035556e6769d3724a8ee97d87c3faaac` adds requirements frozen per
specification revision. Against `--requirements 2026-07-28`, Python MCP
`2.1.1` passed all 372 scored client checks across 32 scenarios and all 119
scored server checks across 37 scenarios. There is no expected-failure
baseline.

Seven later client scenarios and thirteen later server scenarios also ran for
visibility. Their auth, JSON Schema, and Tasks failures remain explicit and
unscored because they were added after the frozen release requirements. This
classification removes the former false retroactive blocker without hiding
future work.

## Independent gates

P1-01 through P1-14 pass. P1-11 passed independently through the exact
OS Abyss Codex/abyss-stack production Tasks pair, not through Python SDK core
conformance or upstream Codex literals. The admitted subset is extension
advertisement, create, completed get, cancel, cancelled get, auth and owner
binding, observe-only output, and missing-extension denial. Update/input-required,
notifications, and distributed poll enforcement remain outside that subset.

The isolated MCP `2.1.1` core-read candidate is protocol-ready, but production
core-read migration remains blocked until the deployment-bound fleet, rollback,
and Tasks receipts are refreshed against the candidate SDK and rechecked for
currentness. Candidate and deployment deadlines remain separate; the overall
deadline is the earliest of both, and changing a stale receipt's SDK label
cannot revive it. Three candidate contours and one internal-effect contour
remain inactive and unadmitted.
External effects remain outside this decision.

## Supporting behavior receipts

The exact isolated receipts separately prove:

- stateless `server/discover` and self-describing requests;
- principal-bound opaque `requestState`, expiry, tamper rejection,
  cross-request replay denial, and key-retirement revocation;
- private TTL cache hits and expiry;
- `subscriptions/listen` addition/removal invalidation;
- stale-catalog inability to authorize a removed tool;
- explicit refresh after a disconnected listener.

These are bounded read proofs. The live fleet receipt additionally proves
production admission and exact modern wire for the eleven named units; it does
not prove multi-replica fan-out or effectful replay safety.

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
upstream identities and acts as a TTL backstop. Neither unit starts or restarts
organs. Admission refresh can republish only already-owner-reviewed read
authority against fresh exact deployment and canary evidence; new authority
still requires a separate owner decision.
