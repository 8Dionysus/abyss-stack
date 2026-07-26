# Sync Wrapper

Routes `scripts/aoa-sync-federation-surfaces` and
`mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh`.

The wrapper mirrors selected sibling surfaces for runtime consumption; it does
not make abyss-stack the owner of those surfaces.

`--check --json` verifies both required mirrored files and the mirror manifest
freshness when the sibling source checkout exposes a Git commit. A mismatch
between the source checkout `HEAD` and
`manifest/federation_mirror_manifest.json.source_git_commit` is reported as
`status:"stale"` with exit code `1`.

The check also validates the manifest schema, layer, authority denial, exact
required-file list, and SHA-256 of every required mirrored file. A byte change
behind an unchanged source ref is `status:"invalid_manifest"`, not healthy.
Stable `aoa-routing` mirror paths are resolved from the owner's current
source-home topology: core schemas come from `routing/core/`, while
federation-entry, recurrence, and ToS-KAG boundary surfaces stay in their
owning mechanic parts. The runtime mirror keeps its compatibility paths; it
does not require the owner repository to restore retired flat source paths.

Use `--check --sync-if-stale --json --layer <layer>` for explicit maintenance
automation. The command performs the same check first, refreshes the mirror only
when the check is degraded, and then emits one final JSON check payload with
`synced:true` when a repair happened.

The routing candidate used during SDK succession may have no native Git source
ref. In that isolated case the sync check reports
`freshness_status:"source_commit_unavailable"` while still checking every
content hash. That is content evidence only; route-api provenance and trust
closure remain degraded until an admitted runtime manifest supplies both.
The admission field is a full `abyss_machine_artifact_trust_gate_v1` runtime
result bound to an artifact subject digest and latest durable record; a bare
`allow` value is not sufficient.

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
