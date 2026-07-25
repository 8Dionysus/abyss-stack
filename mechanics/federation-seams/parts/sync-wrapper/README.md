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

`materialize --isolated` creates a rehearsal mirror. Replacing an existing
target requires a disjoint sibling `--rollback-root`.
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
