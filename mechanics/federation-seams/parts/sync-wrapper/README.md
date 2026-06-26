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

Use `--check --sync-if-stale --json --layer <layer>` for explicit maintenance
automation. The command performs the same check first, refreshes the mirror only
when the check is degraded, and then emits one final JSON check payload with
`synced:true` when a repair happened.
