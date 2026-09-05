# Protocol Migration Contract

## Inputs

The lab consumes:

1. an exact stable specification revision;
2. an exact next specification revision and release status;
3. exact stable and next SDK revisions;
4. an exact official conformance-suite revision;
5. an observed consumer version and pair-level evidence;
6. Abyss-specific conformance, canary, dual-support, and rollback receipts.

Every drift trigger invalidates the current observation until it is refreshed.
Protocol strings discovered inside a binary are navigation evidence only.

## Admission

Production migration is allowed only when:

- the next specification is final and production-allowed;
- a stable, production-allowed SDK supports its wire version;
- Codex and the exact server pair are observed on that wire;
- `server/discover`, stateless behavior, explicit handles, and trace/cache
  behavior are observed;
- official and Abyss pair-conformance pass;
- compatibility aliases, dual support, and rollback pass;
- the isolated read-only `aoa-kag` canary passes;
- all core-read P1 gates are `passed`; P1-11 is an independent Tasks extension
  gate and can pass only for the explicitly bounded Tasks production subset.
- every admitted production unit has an exact production process identity,
  deployment-bound canary, current registry record, modern-only negative wire
  proof, and zero bootstrap identity;
- deployment-bound receipts must match the candidate SDK version and remain
  current through their individual expiry deadlines; the derived overall
  evidence deadline includes the stable rollback, Tasks matrix, live-fleet,
  and production-Tasks receipts, and an isolated source candidate never
  upgrades a production claim;
- no executable legacy template or enabled legacy instance remains.

The derived status reports five separate verdicts:

- `core_read_migration_allowed`;
- `tasks_extension_allowed`;
- `candidate_migration_allowed`;
- `internal_effect_migration_allowed`;
- `external_effect_migration_allowed`.

The KAG protocol pilot can advance only the first two lab facts: whether a
read-only pilot may run and whether it completed. Candidate and effect
verdicts remain false until their own owner, proof, approval, and rollback
contracts exist.

Adapter-level proof and consumer-level proof are independent. A Python
next-era adapter may pass `server/discover`, stateless, and Abyss behavior
checks while Codex remains on the stable wire. Such a receipt advances only
the corresponding adapter gates and cannot enable registration or migration.
Likewise, an isolated read call is not the registered consumer canary.

For the first read-only pilot, `requestState` is treated as an explicit
application handle. Its minimum proof is opacity, per-request bearer
verification, principal isolation, expiry, request binding, tamper rejection,
and key-retirement revocation. Exact same-request replay may be allowed only
for a declared idempotent read result. No such allowance carries into
candidate or effect tools.

Catalog cache entries are discovery only. A private TTL bounds staleness;
`subscriptions/listen` invalidates and revokes entries while connected; a
dropped listener receives no replay and must refetch; explicit refresh is the
consumer recovery path. A tool removed at the server must remain uncallable
even while an old catalog entry is still warm. Cross-replica invalidation
requires its own production subscription-bus receipt.

Tasks remains a separately versioned extension gate. Python MCP `2.1.1` does
not implement the Tasks client extension, and upstream Codex `0.147.0` does
not advertise it. The bounded OS Abyss derivative does advertise
`io.modelcontextprotocol/tasks` on the real production pair and passes
create/get/cancel, owner binding, observe-only result, auth, and capability
negatives. Type literals or core conformance still cannot pass that gate.

The feature-gated Abyss adapter may be exercised before a capable external
consumer exists. Such a synthetic pilot proves only adapter/store behavior. A
real Tasks consumer must advertise the extension per request and pass the same
wire, auth, restart, input, cancellation, TTL, and owner-bound result checks
before P1-11 can pass. That exact bounded production pair has now passed P1-11.
Update/input-required, notifications, and distributed poll enforcement remain
explicitly outside its admitted subset until their own receipts exist.

Released Rust `rmcp 3.1.2` is the first real external reference client to pass
the strict adapter boundary for discovery, create, `tasks/get`, task-bound
headers, completed results, preserved owner errors, and unknown-task denial.
That reference pair does not by itself prove OS Abyss production deployment;
it remains independent corroboration rather than the production consumer.

MCP Inspector `2.1.0` remains blocked against the strict adapter. Its raw
`tasks/get` request supplies `Mcp-Method` but omits task-bound `Mcp-Name`; the
adapter returns JSON-RPC `-32020` with HTTP `400`. The boundary must not be
weakened to accommodate this client. The removal condition is a client request
that binds `Mcp-Name` to the task ID, followed by an unchanged-adapter retest.
Neither the released-rmcp pass nor the Inspector blocker changes the exact
OS Abyss Codex production-pair verdict.

## Dual support and rollback

`aoa_kag_next_lab` remains a removable isolated candidate contour. The current
source candidate uses Python MCP `2.1.1`, while deployment-bound production
receipts remain explicitly on MCP `2.0.0` until a separate deployment proof.
Expired deployment receipts remain historical and cannot be made current by
changing their recorded SDK label. Rollback is a coherent source/runtime
restore followed by fresh canary,
registry, preflight, and production-wire proof; mixed-era source/runtime states
are invalid. The cold MCP 1 runtime is never an active compatibility route.

## Watcher

The watcher fingerprints only stable identities: selected upstream release
fields, conformance commit, exact Codex bytes/version/features, local behavior
source bytes, and the generated protocol status. Response digests and headers
remain evidence but do not cause irrelevant identity churn.

Tasks matrix, pilot, strict-pair fixtures and runners are watched beside Rust,
C#, Go and Inspector release signals. Their drift requests a fresh isolated
Tasks lab but cannot turn a Tasks-only incompatibility into a core-read blocker.

A new identity, missing successful baseline, or approaching evidence TTL
requests a new lab. Required observation failure blocks execution. The private
runtime config is mode `0600`, uses argv arrays without a shell, reads only
mode `0600` non-symlink secret files, and names required private/public-safe
receipts. Every run gets an immutable private input snapshot. Only a zero-exit
suite with all receipts and byte-identical protected production paths advances
the last-success fingerprint.

The watcher has no production admission or lifecycle authority. A trigger,
successful suite, or public-safe verdict cannot enable a feature globally,
replace a registration, refresh registry acceptance, restart an organ, or
authorize a cutover.

Machine-local paths and raw errors remain private watcher evidence. The
public-safe status contains only content identities, bounded error classes,
reason codes, and path-free receipt metadata.

Each run records a private `run-state.json` (`running`, `completed`, or
`failed`) beside its immutable input and execution receipts. The retention
policy in `protocol-watch-plan.v1.json` treats `stable-home`,
`lab/codex-home`, and `step-logs` as the only disposable run roots and reports
their nested plugin cache roots separately. It keeps
the last successful and operator-pinned runs, active runs, the newest failed
diagnostics, the current observation, and required receipt files. Older
completed runs are first copied to the private `retained-receipts/` archive,
verified, and then removed. Ownership, regular-file, symlink, inode, device,
and mount-boundary checks are required before an operation is emitted or
applied. A plan is a dry run; `--retention-apply` rechecks every path and byte
count under the state lock before changing it. Operator pins use a private
mode `0600` `pinned-runs.json` object containing a `run_ids` array; malformed
or missing references suppress all destructive operations.

The hourly service uses `--apply-retention` after its normal lab pass. The
source-generated protocol status remains the TTL authority: a successful lab
does not refresh that generated evidence, so an unchanged expired source
continues to report `evidence_ttl_due` until its owner refreshes the source
status.

## Claim limits

A green source validator proves the source posture and deterministic gating.
The exact final specification and stable SDK pins are source evidence. They do
not prove a modern Codex wire pair, conformance, deployed parity, registration,
canary benefit, or rollback.
