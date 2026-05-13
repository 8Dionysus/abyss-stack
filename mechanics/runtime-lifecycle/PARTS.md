# Runtime Lifecycle Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Layout install | `parts/layout-install/` | `scripts/aoa-install-layout`, `scripts/aoa-check-layout`, `parts/layout-install/aoa_install_layout.sh`, `parts/layout-install/aoa_check_layout.sh`, `docs/PATHS.md`, `docs/STORAGE_LAYOUT.md` |
| First-run bootstrap | `parts/first-run-bootstrap/` | `scripts/aoa-first-run`, `parts/first-run-bootstrap/aoa_first_run.sh`, `docs/FIRST_RUN.md`, `docs/DEPLOYMENT.md` |
| Config sync boundary | `parts/config-sync-boundary/` | `scripts/aoa-sync-configs`, `docs/DEPLOYMENT.md` |
| Start and stop | `parts/start-stop/` | `scripts/aoa-up`, `scripts/aoa-down`, `scripts/aoa-warmup`, `parts/start-stop/aoa_up.sh`, `parts/start-stop/aoa_down.sh`, `parts/start-stop/aoa_warmup.sh`, `compose/profiles/`, `compose/presets/` |
| Wait and smoke | `parts/wait-smoke/` | `scripts/aoa-wait`, `scripts/aoa-smoke`, `scripts/aoa-internal-probes`, `parts/wait-smoke/aoa_wait.sh`, `parts/wait-smoke/aoa_smoke.sh`, `parts/wait-smoke/aoa_internal_probes.sh`, `mechanics/runtime-lifecycle/parts/wait-smoke/docs/INTERNAL_PROBES.md` |
| Logs and status | `parts/logs-status/` | `scripts/aoa-logs`, `scripts/aoa-status`, `parts/logs-status/aoa_logs.sh`, `parts/logs-status/aoa_status.sh`, `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`, `mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md`, `mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md` |
| Status readouts | `parts/status-readouts/` | `mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md`, `mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md`, runtime gateway cache and usage snapshot schemas, examples, and focused tests |
| User unit | `parts/user-unit/` | `systemd/user/podman-compose-abyss.service`, `scripts/aoa-install-systemd`, `parts/user-unit/aoa_install_systemd.sh` |

Do not move these parts until validators and deployment sync expectations are
updated with the movement.
