# Config Projection Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Public templates | `parts/public-templates/` | `config-templates/`, `config-templates/AGENTS.md` |
| Env examples | `parts/env-examples/` | `env/`, `env/AGENTS.md` |
| Bootstrap | `parts/bootstrap/` | `scripts/aoa-bootstrap-configs`, `parts/bootstrap/aoa_bootstrap_configs.sh`, `mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md` |
| Sync | `parts/sync/` | `scripts/aoa-sync-configs`, `parts/sync/aoa_sync_configs.sh`, `parts/sync/scripts/mcp_deployment_manifest.py`, `parts/sync/schemas/mcp-deployment-manifest.schema.json`, focused part-local tests, `mcp/`, `schemas/`, `stats/`, `quests/`, `QUESTBOOK.md`, `docs/install/DEPLOYMENT.md` |
| Rendering | `parts/rendering/` | `scripts/aoa-render-config`, `scripts/aoa-render-services`, `scripts/aoa-preset-profiles`, `scripts/aoa-profile-modules`, `scripts/aoa-profile-endpoints`, `parts/rendering/aoa_*.sh`, `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`, `parts/rendering/manifests/runtime_config.bundle.json`, `parts/rendering/scripts/validate_abyss_machine_runtime_config_bundle.py` |
| Codex hooks | `parts/codex-hooks/` | owner/native hook fragments, `parts/codex-hooks/scripts/render_codex_hooks.py`, fragment and composition-receipt schemas, focused atomic-composition tests |
| Deployment paths | `parts/deployment-paths/` | `docs/runtime/PATHS.md`, `docs/runtime/STORAGE_LAYOUT.md` |

Do not move these parts until template consumers and validators follow.
