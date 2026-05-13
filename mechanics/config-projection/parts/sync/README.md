# Sync

Routes config sync helpers and deployment docs:
`scripts/aoa-sync-configs`,
`mechanics/config-projection/parts/sync/aoa_sync_configs.sh`, and
`docs/DEPLOYMENT.md`.

Sync owns source-to-runtime projection behavior. It must not become a Git mirror
of live private machine state.
