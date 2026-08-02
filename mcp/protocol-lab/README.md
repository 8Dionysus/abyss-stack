# MCP Protocol Lab

This district holds the source-side compatibility gate for an OS Abyss MCP
protocol migration. It does not select a new production protocol merely
because a specification, SDK, or client advertises support.

Current posture after the 2026-07-28 final release:

- observed Codex production-compatible wire version: `2025-11-25`;
- next candidate: final `2026-07-28`;
- stable next SDKs: Python `2.0.0`, TypeScript client/server `2.0.0`;
- Codex `0.146.0`: the production `aoa_kag` inventory and call remain on the
  stable route; it is not a modern production consumer;
- Codex `0.147.0-alpha.4`: an isolated binary with
  `mcp_2026_07_28` explicitly enabled passed a separately named,
  separately credentialed `aoa_kag_next_lab` call on the actual
  `2026-07-28` wire; it has no production authority;
- current conformance source: exact commit `81eb1c3`; the Python `2.0.0`
  server fixture passed `40` checks in the twenty scenarios exposed by its
  SDK runner, while the client fixture passed `372` and failed two checks
  because it does not recognize the new
  `json-schema-2020-12-preservation` scenario; no baseline masks the gap;
- isolated KAG adapter pair: `2026-07-28` `server/discover`, stateless
  requests, private TTL caching, trace propagation, and read-only denials
  pass; exact projection and owner freshness are current;
- cancellation propagation: failed; cancelling the client request did not
  stop server dispatch, and the handler completed after client cancellation;
- isolated KAG `requestState` handles: bearer-bound round trip, principal
  isolation, expiry, cross-request replay denial, tamper denial, and
  key-retirement revocation pass; exact same-request replay is allowed only
  for the idempotent read tool;
- isolated KAG catalog cache: private TTL hit/expiry, subscription
  invalidation, tool-removal revocation, no-listener staleness, and explicit
  refresh pass; a stale catalog cannot authorize a removed tool;
- registered prerelease canary: exact one-tool inventory, deterministic schema
  digest, authenticated principal, trace propagation, wrong-bearer `401`,
  16 KiB input and 256 KiB output bounds, and oversized-input denial pass;
- rollback: the lab process, port, credential, registration, and isolated
  `CODEX_HOME` were removed; the operator config stayed byte-identical and
  the existing `aoa_kag` registration passed a post-rollback call;
- Python MCP `2.0.0` Tasks extension: not implemented;
- registered read-only prerelease canary and rollback: passed;
- complete modern pair and production core-read migration: blocked by current
  conformance mismatch, failed cancellation propagation, and absence of a
  production-eligible modern Codex pair;
- Tasks, candidate, internal-effect, and external-effect migration: separately
  blocked;
- stable registration: `aoa_kag`;
- isolated lab registration: `aoa_kag_next_lab`, removed after proof;
- first pilot: compact read-only `aoa-kag`;
- candidate and effect organs: excluded.

The matrix pins exact specification, SDK, conformance-suite, and consumer
observations. The generated v2 status reports separate core-read, Tasks,
candidate, internal-effect, and external-effect verdicts. Tasks no longer
blocks interpretation of the core-read gate, and a passed prerelease pilot
does not authorize production cutover.

## Source map

| Surface | Meaning |
|---|---|
| `protocol-compatibility-matrix.v1.json` | authored stable/next comparison, exact pins, gates, alias and pilot law |
| `fixtures/current-pair-observation.json` | current evidence-backed pair observation |
| `fixtures/codex-0.146.0-production-pair-observation.json` | public-safe derivative of the registered production inventory and direct call; not a next-protocol canary |
| `fixtures/codex-0.146.0-wire-observation.json` | normalized receipt for the isolated Codex-to-Python-SDK stdio exchange |
| `fixtures/python-mcp-2.0.0-conformance-observation.json` | normalized exact-SDK official conformance receipt with raw-result digests |
| `fixtures/codex-0.147.0-alpha.4-kag-next-lab-observation.json` | public-safe actual modern Codex registration, wire, call, limits, and rollback proof |
| `fixtures/codex-0.146.0-stable-kag-post-rollback-observation.json` | actual operator-config stable KAG canary after lab removal |
| `fixtures/kag-next-pair-observation.json` | normalized isolated KAG next-adapter pair receipt and its claim limits |
| `fixtures/kag-handle-pair-observation.json` | normalized read-only requestState isolation, expiry, replay, and revocation receipt |
| `fixtures/kag-cache-pair-observation.json` | normalized private TTL, invalidation, stale-catalog, and revocation receipt |
| `scripts/run_kag_next_pair.py` | private raw-receipt runner for the isolated KAG adapter |
| `scripts/run_kag_handle_pair.py` | private raw-receipt runner for bearer-bound KAG requestState handles |
| `scripts/run_kag_cache_pair.py` | private raw-receipt runner for KAG catalog cache behavior |
| `scripts/run_codex_kag_next_lab.py` | removable exact Codex prerelease lab plus stable post-rollback canary runner |
| `schemas/` | machine-readable input and derived-status contracts |
| `generated/protocol-lab-status.json` | deterministic, rebuildable migration verdict |
| `scripts/build_protocol_lab_status.py` | pure status builder |
| `scripts/validate_protocol_lab.py` | fail-closed source and stack-pin validator |
| `tests/` | mutation and migration-gate tests |

The modern Codex receipt passes the prerelease consumer and registered-read
canary gates only. It does not make the prerelease production-eligible, repair
the current conformance fixture mismatch, prove cancellation propagation or subscription fan-out across
replicas, or authorize candidate/effect migration.

Read [CONTRACT.md](CONTRACT.md) for admission law and
[docs/COMPATIBILITY_MATRIX.md](docs/COMPATIBILITY_MATRIX.md) for the refresh
workflow.
