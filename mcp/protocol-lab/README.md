# MCP Protocol Lab

This district holds the source-side compatibility gate for an OS Abyss MCP
protocol migration. It does not select a new production protocol merely
because a specification, SDK, or client advertises support.

Current posture after the 2026-07-28 final release:

- observed Codex production-compatible wire version: `2025-11-25`;
- next candidate: final `2026-07-28`;
- stable next SDKs: Python `2.0.0`, TypeScript client/server `2.0.0`;
- Codex `0.146.0`: the production `aoa_kag` app-server inventory and call
  observe `2025-11-25`; a separate isolated Python MCP `2.0.0` probe falls
  back to `2025-06-18`, not `2026-07-28`;
- latest public conformance release: `v0.1.16`, with no observed final-protocol
  suite; the exact tested next conformance package remains
  `0.2.0-alpha.10`; exact Python SDK
  server/client checks pass `114/371` with zero failures, but this is not
  Codex or Abyss-adapter conformance;
- isolated KAG adapter pair: `2026-07-28` `server/discover`, stateless
  requests, private TTL caching, trace propagation, and read-only denials
  pass; exact projection is current while owner freshness is
  `source_unavailable`;
- isolated KAG `requestState` handles: bearer-bound round trip, principal
  isolation, expiry, cross-request replay denial, tamper denial, and
  key-retirement revocation pass; exact same-request replay is allowed only
  for the idempotent read tool;
- isolated KAG catalog cache: private TTL hit/expiry, subscription
  invalidation, tool-removal revocation, no-listener staleness, and explicit
  refresh pass; a stale catalog cannot authorize a removed tool;
- Python MCP `2.0.0` Tasks extension: not implemented;
- next migration: blocked;
- stable registration: `aoa_kag`;
- isolated future lab registration: `aoa_kag_next_lab`, disabled;
- first pilot: compact read-only `aoa-kag`;
- candidate and effect organs: excluded.

The matrix pins exact specification, SDK, conformance-suite, and consumer
observations. The pair observation records which runtime receipts actually
exist. The generated status is derived from both and remains fail-closed until
all fourteen P1 gates pass.

## Source map

| Surface | Meaning |
|---|---|
| `protocol-compatibility-matrix.v1.json` | authored stable/next comparison, exact pins, gates, alias and pilot law |
| `fixtures/current-pair-observation.json` | current evidence-backed pair observation |
| `fixtures/codex-0.146.0-production-pair-observation.json` | public-safe derivative of the registered production inventory and direct call; not a next-protocol canary |
| `fixtures/codex-0.146.0-wire-observation.json` | normalized receipt for the isolated Codex-to-Python-SDK stdio exchange |
| `fixtures/python-mcp-2.0.0-conformance-observation.json` | normalized exact-SDK official conformance receipt with raw-result digests |
| `fixtures/kag-next-pair-observation.json` | normalized isolated KAG next-adapter pair receipt and its claim limits |
| `fixtures/kag-handle-pair-observation.json` | normalized read-only requestState isolation, expiry, replay, and revocation receipt |
| `fixtures/kag-cache-pair-observation.json` | normalized private TTL, invalidation, stale-catalog, and revocation receipt |
| `scripts/run_kag_next_pair.py` | private raw-receipt runner for the isolated KAG adapter |
| `scripts/run_kag_handle_pair.py` | private raw-receipt runner for bearer-bound KAG requestState handles |
| `scripts/run_kag_cache_pair.py` | private raw-receipt runner for KAG catalog cache behavior |
| `schemas/` | machine-readable input and derived-status contracts |
| `generated/protocol-lab-status.json` | deterministic, rebuildable migration verdict |
| `scripts/build_protocol_lab_status.py` | pure status builder |
| `scripts/validate_protocol_lab.py` | fail-closed source and stack-pin validator |
| `tests/` | mutation and migration-gate tests |

The isolated receipts advance only adapter-owned gates. They do not enable the
disabled registration, satisfy the Codex consumer gate, prove subscription
fan-out across replicas, prove effectful handle replay safety, or count as the
registered read canary.

Read [CONTRACT.md](CONTRACT.md) for admission law and
[docs/COMPATIBILITY_MATRIX.md](docs/COMPATIBILITY_MATRIX.md) for the refresh
workflow.
