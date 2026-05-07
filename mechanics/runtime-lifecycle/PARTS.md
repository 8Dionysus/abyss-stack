# Runtime Lifecycle Parts

| Part | Current source surfaces |
|---|---|
| Layout install | `scripts/aoa-install-layout`, `scripts/aoa-check-layout`, `docs/PATHS.md`, `docs/STORAGE_LAYOUT.md` |
| Config sync boundary | `scripts/aoa-sync-configs`, `docs/DEPLOYMENT.md` |
| Start and stop | `scripts/aoa-up`, `scripts/aoa-down`, `compose/profiles/`, `compose/presets/` |
| Wait and smoke | `scripts/aoa-wait`, `scripts/aoa-smoke`, `docs/INTERNAL_PROBES.md` |
| Logs and status | `scripts/aoa-logs`, `scripts/aoa-status`, `docs/RENDER_TRUTH.md` |
| User unit | `systemd/user/podman-compose-abyss.service`, `scripts/aoa-install-systemd` |

Do not move these parts until validators and deployment sync expectations are
updated with the movement.

