# MCP Protocol Lab

This district holds the source-side compatibility gate for an OS Abyss MCP
protocol migration. It does not select a new production protocol merely
because a specification, SDK, or client advertises support.

Current posture after the 2026-07-28 final release:

- admitted OS Abyss production wire: final `2026-07-28`;
- stable next SDKs: Python `2.0.0`, TypeScript client/server `2.0.0`;
- all fifteen standalone stack-owned organ packages pin exact `mcp==2.0.0`;
- eleven production read units are deployment-bound, canary-proven, admitted,
  and observed through `server/discover` and `tools/list` on the exact modern
  wire; wrong bearers and legacy `initialize` are denied before session issue;
- no active or enabled legacy owner instance remains; the old shared template
  is a non-startable tombstone and the MCP 1 runtime is cold rollback material;
- OS Abyss Codex `0.147.0-abyss.2` selects modern MCP only for the explicit
  admitted organ allow-list and keeps unrelated external MCP owners outside
  this claim;
- that production Codex/abyss-stack pair advertises
  `io.modelcontextprotocol/tasks` and passes bounded create, completed get,
  cancel, cancelled get, owner binding, observe-only result, and missing
  extension denial;
- Tasks update/input-required, notifications, and distributed poll enforcement
  remain outside the admitted subset without blocking the proven lifecycle;
- three candidate units and one internal-effect unit also pass modern-only
  discovery and legacy denial, but no tool was invoked, no non-read contour is
  admitted, and all four were returned to `inactive`;
- admission refresh, preflight sweep, and admission keeper preserve currentness
  without starting or restarting organs;
- the same exact stable binary, with `mcp_2026_07_28` enabled only in a
  removable `CODEX_HOME`, previously passed the isolated
  `aoa_kag_next_lab` precursor proof;
- the same exact stable binary, with `mcp_2026_07_28` enabled only in a
  removable `CODEX_HOME`, passed the separately named and credentialed
  `aoa_kag_next_lab` call on the actual `2026-07-28` wire;
- official conformance commit `c321dd3` freezes requirements per specification
  revision. Python `2.0.0` passed all 372 scored client checks and all 119
  scored server checks for `2026-07-28`; later unscored auth, JSON Schema, and
  Tasks failures remain visible;
- isolated KAG adapter pair: `2026-07-28` `server/discover`, stateless
  requests, private TTL caching, trace propagation, and read-only denials
  pass; exact projection and owner freshness are current;
- cancellation propagation: the SSE disconnect path cancelled both the client
  request and server dispatch, and the handler did not complete afterward;
- isolated KAG `requestState` handles: bearer-bound round trip, principal
  isolation, expiry, cross-request replay denial, tamper denial, and
  key-retirement revocation pass; exact same-request replay is allowed only
  for the idempotent read tool;
- isolated KAG catalog cache: private TTL hit/expiry, subscription
  invalidation, tool-removal revocation, no-listener staleness, and explicit
  refresh pass; a stale catalog cannot authorize a removed tool;
- registered stable modern lab canary: exact one-tool inventory, deterministic schema
  digest, authenticated principal, trace propagation, wrong-bearer `401`,
  16 KiB input and 256 KiB output bounds, and oversized-input denial pass;
- rollback: the lab process, port, credential, registration, and isolated
  `CODEX_HOME` were removed; the operator config stayed byte-identical and
  the existing `aoa_kag` registration passed a post-rollback call;
- Python MCP `2.0.0` does not itself implement the Tasks client extension;
- feature-gated Abyss Tasks adapter: 11/11 synthetic lifecycle cases pass,
  including restart recovery and one real read-only owner diagnostic; Codex was
  not the Tasks client and notifications remain unproved;
- released Rust `rmcp 3.1.2`: passed an isolated strict pair against the same
  feature-gated adapter, including extension advertisement, task creation,
  `tasks/get`, task-bound `Mcp-Method`/`Mcp-Name`, completed result recovery,
  owner error preservation, and unknown-task denial; this is reference-client
  evidence, not production admission;
- MCP Inspector `2.1.0`: its own Tasks integration suite passes, and task
  creation reaches the Abyss adapter, but the strict pair is blocked because
  raw `tasks/get` omits task-bound `Mcp-Name`; the adapter correctly retains
  the boundary with JSON-RPC `-32020` / HTTP `400`;
- isolated read-only modern pair and rollback: passed;
- production core-read migration: passed;
- bounded production Tasks lifecycle: passed;
- candidate and internal-effect protocol readiness: passed, while their
  authority migration remains false;
- external-effect migration: false;
- stable registration: `aoa_kag`;
- isolated lab registration: `aoa_kag_next_lab`, removed after proof;
- first pilot: compact read-only `aoa-kag`;
- candidate and effect authority: excluded.

The matrix pins exact specification, SDK, conformance-suite, and consumer
observations. All fourteen P1 gates pass, including the independently evidenced
bounded Tasks gate.
The generated v2 status reports separate core-read, Tasks, candidate,
internal-effect, and external-effect verdicts. Protocol readiness never grants
candidate or effect authority.

## Protocol watcher

`protocol-watch-plan.v1.json` watches current Codex binary and feature output,
published MCP/Python/TypeScript/Go/Rust/C# SDK and Inspector versions,
conformance `main`, exact local core and Tasks behavior sources, and evidence
TTL. `scripts/protocol_watcher.py` creates an immutable private
input observation, compares content-addressed identities with the last
successful lab, and emits a normalized public-safe status. On drift or TTL it
may execute a private multi-step runtime plan in a unique `0700` run root.

Every child step is argv-based rather than shell-evaluated. Secret files must
be regular non-symlink mode `0600`; their values are neither logged nor
published. Required receipts are hashed and private receipts must be mode
`0600`. Protected production files are measured before and after the suite.
Only a successful suite advances `last-success.json`; failure, missing network
evidence, missing runtime config, changed protected bytes, or missing receipts
remain fail-closed. The watcher never starts, stops, restarts, registers, or
migrates a production contour itself.

The private status retains exact machine-local refs for diagnosis. Its
`public-safe.json` projection replaces those refs with content identities,
reduces blocked observations to error classes and reason codes, and strips
local paths and raw child errors.

The source-managed `abyss-mcp-protocol-watch.path` reacts to local Codex and
lab-source changes. Its hourly timer discovers upstream release/conformance
changes and acts as a TTL backstop. Linking these units does not enable them,
and an operator-private runtime plan remains required before an automatic lab
can execute.

## Source map

| Surface | Meaning |
|---|---|
| `protocol-compatibility-matrix.v1.json` | authored stable/next comparison, exact pins, gates, alias and pilot law |
| `fixtures/current-pair-observation.json` | current evidence-backed pair observation |
| `fixtures/codex-0.146.0-production-pair-observation.json` | public-safe derivative of the registered production inventory and direct call; not a next-protocol canary |
| `fixtures/codex-0.146.0-wire-observation.json` | normalized receipt for the isolated Codex-to-Python-SDK stdio exchange |
| `fixtures/python-mcp-2.0.0-frozen-conformance-observation.json` | normalized official frozen-revision conformance receipt with raw-result digests |
| `fixtures/codex-0.147.0-stable-kag-next-lab-observation.json` | public-safe stable modern Codex registration, wire, call, limits, and rollback proof |
| `fixtures/codex-0.147.0-stable-kag-post-rollback-observation.json` | actual operator-config stable KAG canary after lab removal |
| `fixtures/kag-next-cancellable-pair-observation.json` | normalized isolated KAG next-adapter and propagated-cancellation receipt |
| `fixtures/kag-handle-pair-current-observation.json` | current normalized read-only requestState isolation, expiry, replay, and revocation receipt |
| `fixtures/kag-cache-pair-current-observation.json` | current normalized private TTL, invalidation, stale-catalog, and revocation receipt |
| `fixtures/tasks-adapter-pilot-20260808.json` | public-safe feature-gated Tasks lifecycle and read-only owner-pilot receipt; not production or Codex proof |
| `tasks-compatibility-matrix.v1.json` | exact per-consumer Tasks feature and wire verdicts, kept independent from the core migration matrix |
| `fixtures/rmcp-3.1.2-tasks-adapter-pair-20260808.json` | released Rust reference-client proof against the strict feature-gated Abyss adapter |
| `fixtures/inspector-2.1.0-tasks-strict-pair-blocked-20260808.json` | exact Inspector strict-pair blocker without weakening task-bound routing |
| `fixtures/live-modern-fleet-20260809.json` | compact production read-fleet, automation, rollback, and non-read protocol observation |
| `fixtures/codex-tasks-production-pair-20260809.json` | bounded OS Abyss Codex Tasks production-pair receipt |
| `scripts/run_kag_next_pair.py` | private raw-receipt runner for the isolated KAG adapter |
| `scripts/run_kag_handle_pair.py` | private raw-receipt runner for bearer-bound KAG requestState handles |
| `scripts/run_kag_cache_pair.py` | private raw-receipt runner for KAG catalog cache behavior |
| `scripts/run_codex_kag_next_lab.py` | removable exact stable Codex modern lab plus stable post-rollback canary runner |
| `scripts/run_tasks_adapter_pilot.py` | private synthetic Tasks lifecycle runner with one real read-only owner diagnostic |
| `scripts/run_rust_tasks_adapter_pair.py` | isolated released-rmcp client pair runner; emits public-safe evidence and leaves production disabled |
| `scripts/run_inspector_tasks_adapter_pair.py` | strict Inspector pair runner; preserves a bounded public-safe failure receipt when task routing headers are incomplete |
| `scripts/run_codex_stack_tasks_pair.py` | isolated or production Codex/abyss-stack Tasks lifecycle runner |
| `scripts/run_live_modern_read_fleet.py` | exact live eleven-unit modern-only read-fleet verifier |
| `scripts/run_live_nonread_protocol.py` | discovery-only candidate/effect verifier that leaves authority absent and units inactive |
| `protocol-watch-plan.v1.json` | exact local/upstream drift inputs and TTL law |
| `scripts/protocol_watcher.py` | immutable observation, trigger, isolated suite and protected-path gate |
| `schemas/` | machine-readable input and derived-status contracts |
| `generated/protocol-lab-status.json` | deterministic, rebuildable migration verdict |
| `scripts/build_protocol_lab_status.py` | pure status builder |
| `scripts/validate_protocol_lab.py` | fail-closed source and stack-pin validator |
| `tests/` | mutation and migration-gate tests |

The modern production receipts admit only the eleven read contours and the
bounded Tasks lifecycle on `abyss-stack` read. They do not prove subscription
fan-out across replicas or authorize candidate/effect migration.

Read [CONTRACT.md](CONTRACT.md) for admission law and
[docs/COMPATIBILITY_MATRIX.md](docs/COMPATIBILITY_MATRIX.md) for the core
refresh workflow, and
[docs/TASKS_COMPATIBILITY_MATRIX.md](docs/TASKS_COMPATIBILITY_MATRIX.md) for
the separately gated Tasks ecosystem verdicts.
