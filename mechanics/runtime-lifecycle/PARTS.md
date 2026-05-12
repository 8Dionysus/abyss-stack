# Runtime Lifecycle Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Layout install | `parts/layout-install/` | `scripts/aoa-install-layout`, `scripts/aoa-check-layout`, `docs/PATHS.md`, `docs/STORAGE_LAYOUT.md` |
| Config sync boundary | `parts/config-sync-boundary/` | `scripts/aoa-sync-configs`, `docs/DEPLOYMENT.md` |
| Start and stop | `parts/start-stop/` | `scripts/aoa-up`, `scripts/aoa-down`, `compose/profiles/`, `compose/presets/` |
| Wait and smoke | `parts/wait-smoke/` | `scripts/aoa-wait`, `scripts/aoa-smoke`, `docs/INTERNAL_PROBES.md` |
| Logs and status | `parts/logs-status/` | `scripts/aoa-logs`, `scripts/aoa-status`, `docs/RENDER_TRUTH.md`, `docs/GATEWAY_CACHE_POLICY.md`, `docs/USAGE_BUDGET_POLICY.md` |
| Status readouts | `parts/status-readouts/` | runtime gateway cache and usage snapshot schemas, examples, and focused tests |
| User unit | `parts/user-unit/` | `systemd/user/podman-compose-abyss.service`, `scripts/aoa-install-systemd` |

Do not move these parts until validators and deployment sync expectations are
updated with the movement.
