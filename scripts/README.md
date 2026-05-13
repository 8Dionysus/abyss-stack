# scripts

`scripts/` contains operator-facing wrappers and repository validators for
`abyss-stack`.

These files stay at the source root because deployment sync copies them into
the runtime `Configs/scripts/` command surface. Mechanic pages own the meaning
and part routes; this directory owns stable command entrypoints.

## Command Groups

| Group | Commands | Owning route |
|---|---|---|
| Layout and sync | `aoa-install-layout`, `aoa-sync-configs`, `aoa-bootstrap-configs`, `aoa-check-layout` | [config projection](../mechanics/config-projection/README.md), [runtime lifecycle](../mechanics/runtime-lifecycle/README.md) |
| Lifecycle wrappers | `aoa-up`, `aoa-down`, `aoa-status`, `aoa-logs`, `aoa-wait`, `aoa-smoke`, `aoa-install-systemd` | [runtime lifecycle](../mechanics/runtime-lifecycle/README.md) |
| Compose introspection | `aoa-preset-profiles`, `aoa-profile-modules`, `aoa-profile-endpoints`, `aoa-render-services`, `aoa-render-config` | [config projection rendering](../mechanics/config-projection/parts/rendering/README.md) |
| Diagnostics | `aoa-doctor`, `aoa-diagnose`, `aoa-internal-probes`, `build_diagnostic_surface_catalog.py`, `validate_diagnostic_surface_catalog.py` | [diagnostic spine](../mechanics/diagnostic-spine/README.md) |
| Machine fit | `aoa-host-facts`, `aoa-machine-bridge`, `aoa-machine-fit`, `aoa-platform-adaptation` | [machine fit](../mechanics/machine-fit/README.md) |
| Inference pilots | `aoa-qwen-run`, `aoa-qwen-check`, `aoa-qwen-bench`, `aoa-llamacpp-pilot`, `aoa-langgraph-pilot`, `aoa-local-ai-trials`, `aoa-long-horizon-pilot`, `aoa-bounded-autonomy-pilot`, `aoa-runtime-bench-index` | [inference pilots](../mechanics/inference-pilots/README.md) |
| Governed execution | `aoa-governed-run`, `aoa-export-memo-candidate`, `aoa-export-runtime-evidence-selection`, `aoa-export-artifact-hook-candidate`, `aoa-run-memo-contradiction-integrity` | [governed execution](../mechanics/governed-execution/README.md) |
| Federation and RPG seams | `aoa-federated-check`, `aoa-sync-federation-surfaces`, `aoa-rpg-runtime-projection` | [federation seams](../mechanics/federation-seams/README.md) |
| Repair adapters | `aoa-a2a-return-closeout-dry-run` | [runtime repair](../mechanics/runtime-repair/README.md) |
| Repository validation | `validate_stack.py`, `validate_nested_agents.py`, `release_check.py` | root `AGENTS.md`, [mechanics artifact topology](../mechanics/ARTIFACT_TOPOLOGY.md) |
| Windows bridge | `aoa.ps1`, `aoa-doctor-win.ps1`, `aoa-bootstrap-wsl.ps1` | [machine-fit windows bridge](../mechanics/machine-fit/parts/windows-bridge/README.md) |

## Contract

- Keep command names stable unless the route cards, docs, validators, and
  deployment sync behavior move with the change.
- Keep source checkout and deployed runtime paths distinct.
- Keep wrappers public-safe and avoid printing secrets.
- Put mechanic-specific implementation logic under the owning
  `mechanics/<package>/parts/<part>/` route when it can move without breaking
  operator command stability.

See [AGENTS.md](AGENTS.md) for editing rules.
