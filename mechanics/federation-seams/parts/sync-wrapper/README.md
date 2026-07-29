# Sync Wrapper

Routes `scripts/aoa-sync-federation-surfaces` and
`mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh`.

The wrapper mirrors selected sibling surfaces for runtime consumption; it does
not make abyss-stack the owner of those surfaces.

For ordinary sibling-owned layers, `--check --json` verifies both required
mirrored files and manifest freshness when the source checkout exposes a Git
commit. A mismatch between checkout `HEAD` and the manifest source commit is
reported as `status:"stale"` with exit code `1`.

The check also validates the manifest schema, layer, authority denial, exact
required-file list, and SHA-256 of every required mirrored file. A byte change
behind an unchanged source ref is `status:"invalid_manifest"`, not healthy.

`aoa-routing` is intentionally different after G5. Its stable runtime
namespace is produced only by receipt-bound `scripts/aoa-routing-cutover`
from an admitted `aoa-sdk` release. Ordinary federation sync has no routing
source checkout. `--check --layer aoa-routing` performs a read-only
materialized-integrity inspection; sync and `--sync-if-stale` fail closed and
route repair to the cutover workflow.

Use `--check --sync-if-stale --json --layer <layer>` for explicit maintenance
automation of the remaining checkout-backed layers. The command performs the
same check first, refreshes only a degraded mirror, and emits one final JSON
payload with `synced:true` when repair happened. This mode is forbidden for
`aoa-routing`.

## SDK routing canary intake

`scripts/aoa-routing-canary` is the separate fail-closed intake for an exact
`aoa-sdk` routing-producer candidate. It accepts only:

- an `abyss_machine_artifact_subject_store_v1` whose aggregate ledger and every
  materialized byte verify
- a full latest-record `abyss_machine_artifact_trust_gate_v1` verdict for
  `consumer_intent: runtime_canary`
- exact SDK and canonical predecessor Git refs
- a producer-admission object that keeps every G5 authority flag false

`materialize --isolated` creates a rehearsal mirror and rejects the live
target shape. Replacing another existing rehearsal target requires a
disjoint sibling `--rollback-root`.
`materialize --authorized-live-canary` additionally requires the live target
shape `Knowledge/federation/aoa-routing` and a named `--operator-change-ref`;
it still does not authorize a producer switch.
`rollback --authorized-live-canary` restores the predecessor tree and
preserves the displaced SDK candidate at an explicit
`--candidate-retain-root`. Rollback depends only on the three local trees and
the expected candidate identity, so revoked trust or a damaged candidate
cannot block predecessor restoration.

The candidate manifest uses
`routing_producer_posture: sdk_g5_candidate_canary`. Route-api may report
`canary_ready: true` for exact bytes and trust while keeping
`closure_ready: false`. A canary is non-canonical by construction; ordinary
runtime health must not become green until a later, separately reviewed G5
contract changes authority.

## Canonical SDK routing cutover

`scripts/aoa-routing-cutover` is the distinct G5 execution route. It does not
reuse canary authority. It requires:

- an exact subject store materialized for `consumer_intent: runtime`;
- a latest-record `runtime` trust verdict rooted in `public_release`;
- canonical `aoa-sdk` producer admission with the exact predecessor ref;
- the owner-switch receipt as a verified artifact subject at
  `succession/routing-g5-owner-switch.json`;
- the exact G5 authority posture: switch, SDK canonical, live mutation,
  predecessor maintenance-only, and compatibility-window start true, while
  archive authority remains false;
- an explicit rollback root and operator change record for live activation.

Its `inspect-materialized` operation is narrower and read-only: it verifies
the current mirror bytes against the exact subject ledger retained from
external admission, recomputes that ledger's aggregate digest, and verifies
SDK identity, receipt, G5 authority, and embedded trust provenance without
reopening release admission or reading a source checkout. Updating a mirror
file and its manifest hash together cannot replace the retained subject
ledger. Exact-input `check` remains the stronger admission proof.

The mirror posture is `sdk_canonical`. Route-api permits ordinary closure only
for `authorized_live_cutover` when the receipt, producer admission with its
exact trust controls, public-release record, subject bytes, and mirror hashes
agree. An isolated rehearsal may be canonical-ready but cannot close the live
runtime. Runtime rollback first verifies the predecessor manifest, exact
source ref, stable ABI, and all configured file hashes. It then persists
`manifest/routing_g5_compatibility_rollback.json` in the restored tree.
Route-api consumes that marker after restart and keeps ordinary closure red:
the runtime serves compatibility bytes while SDK source ownership remains
canonical. If an atomic swap step fails, the exact staged marker is removed
from the rollback root so that the verified predecessor remains retryable.
If the process terminates, retry validates the exact pre-swap, between-swap,
or already-restored state and safely continues or returns idempotent success.
Trust controls and consumer-intent collections are type-checked before set or
membership operations, so corrupt JSON stays fail-closed without crashing
route-api health or the cutover command.
The isolated mode rejects the live target shape; only
`--authorized-live-cutover` may address
`Knowledge/federation/aoa-routing`.
Live activation fsyncs a validated prepared stage before moving the
predecessor and fsyncs the common parent after each rename. Retry recognizes
the durable prepared-before-swap, between-swaps, and already-activated states.
Rollback applies the same durability law to its marker and tree renames.

## Post-cutover SDK refresh and rollback

Once the live mirror is SDK-canonical, `refresh-materialized` is the only
route that may upgrade an older materialized manifest to the self-contained
subject-ledger contract. It first rechecks every live byte, the exact durable
trust record, owner-switch receipt, SDK and predecessor refs, and G5 authority
against explicit current inputs. It then seals a disjoint sibling
SDK-canonical rollback tree from the admitted subject store before atomically
replacing only the live manifest. The predecessor tree is neither read nor
mutated by this refresh and remains compatibility history.

The refreshed manifest binds `sdk_runtime_rollback` as the primary operational
rollback and marks the predecessor implementation non-required. The
`rollback-sdk --authorized-live-cutover` operation restores that fully embedded
SDK tree using only the live target, SDK rollback tree, routing config, and an
operator change ref. It retains the displaced target, persists
`manifest/routing_sdk_runtime_rollback.json`, fsyncs every transaction
boundary, and resumes safely from pre-swap, between-swap, or already-restored
states. After restart, route-api validates the receipt, reports
`sdk_runtime_rollback_active`, keeps source ownership SDK-canonical, and does
not misreport the restored runtime as a fresh live cutover. Neither route
widens archive authority: `aoa-routing` remains
preserved until consumer-zero, compatibility exit, and separate operator
approval.
