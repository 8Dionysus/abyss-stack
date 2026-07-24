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
