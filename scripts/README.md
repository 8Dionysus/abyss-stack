# scripts

`scripts/` contains operator-facing wrappers and repository validators for
`abyss-stack`.

These files stay at the source root because deployment sync copies them into
the runtime `Configs/scripts/` command surface. Mechanic pages own the meaning
and part routes; this directory owns stable command entrypoints.

All operator command files at this root are thin wrappers. The implementation
bodies live under the owning `mechanics/<package>/parts/<part>/` routes and are
still synced into deployed `Configs/` with the wrappers.

## Command Groups

| Group | Commands | Owning route |
|---|---|---|
| Layout and sync | `aoa-install-layout`, `aoa-sync-configs`, `aoa-bootstrap-configs`, `aoa-check-layout`, `aoa-first-run` | [config projection](../mechanics/config-projection/README.md), [runtime lifecycle](../mechanics/runtime-lifecycle/README.md); implementations under `mechanics/config-projection/parts/{bootstrap,sync}/` and `mechanics/runtime-lifecycle/parts/{layout-install,first-run-bootstrap}/` |
| Lifecycle wrappers | `aoa-up`, `aoa-down`, `aoa-warmup`, `aoa-status`, `aoa-logs`, `aoa-wait`, `aoa-smoke`, `aoa-install-systemd`, `aoa-ovms-admission` | [runtime lifecycle](../mechanics/runtime-lifecycle/README.md); implementations under `mechanics/runtime-lifecycle/parts/{start-stop,logs-status,wait-smoke,user-unit}/` |
| Compose introspection | `aoa-preset-profiles`, `aoa-profile-modules`, `aoa-profile-endpoints`, `aoa-render-services`, `aoa-render-config` | [config projection rendering](../mechanics/config-projection/parts/rendering/README.md); implementations under `mechanics/config-projection/parts/rendering/` |
| Diagnostics | `aoa-doctor`, `aoa-diagnose`, `aoa-internal-probes`, `build_diagnostic_surface_catalog.py`, `validate_diagnostic_surface_catalog.py` | [diagnostic spine](../mechanics/diagnostic-spine/README.md); command backends under diagnostic-spine and runtime-lifecycle parts |
| Machine fit | `aoa-host-facts`, `aoa-machine-bridge`, `aoa-machine-fit`, `aoa-platform-adaptation` | [machine fit](../mechanics/machine-fit/README.md); command backends under `mechanics/machine-fit/parts/` |
| Inference pilots | `aoa-qwen-run`, `aoa-qwen-check`, `aoa-qwen-bench`, `aoa-llamacpp-pilot`, `aoa-langgraph-pilot`, `aoa-local-ai-trials`, `aoa-tos-foundation-lab`, `aoa-long-horizon-pilot`, `aoa-bounded-autonomy-pilot`, `aoa-runtime-bench-index` | [inference pilots](../mechanics/inference-pilots/README.md); command backends under `mechanics/inference-pilots/parts/` |
| Governed execution | `aoa-governed-run`, `aoa-agent-os-runtime`, `aoa-external-actor-bind`, `aoa-external-codex-agent`, `aoa-external-codex-incarnation`, `aoa-external-codex-stasis`, `aoa-export-memo-candidate`, `aoa-export-runtime-evidence-selection`, `aoa-export-artifact-hook-candidate`, `aoa-run-memo-contradiction-integrity` | [governed execution](../mechanics/governed-execution/README.md); command backends under governed-execution and runtime-repair parts |
| Federation, KAG, and RPG seams | `aoa-federated-check`, `aoa-sync-federation-surfaces`, `aoa-routing-canary`, `aoa-routing-cutover`, `aoa-kag-runtime-family`, `aoa-kag-runtime-projection`, `aoa-kag-runtime-eval`, `tos-up`, `aoa-tos-graph`, `aoa-rpg-runtime-projection` | [federation seams](../mechanics/federation-seams/README.md); command backends under `mechanics/federation-seams/parts/` |
| Repair adapters | `aoa-a2a-return-closeout-dry-run` | [runtime repair](../mechanics/runtime-repair/README.md); command backend under `mechanics/runtime-repair/parts/` |
| Repository validation | `ci_gate.py`, `validation_lanes.py`, `run_pytest_lane.py`, `validate_stack.py`, `validate_nested_agents.py`, `validate_local_stats_port.py`, `validate_decision_records.py`, `generate_decision_indexes.py`, `build_workspace_decision_graph.py`, `validate_workspace_decision_graph.py`, `release_check.py` | root `AGENTS.md`, [validation command authority](../docs/validation/COMMAND_AUTHORITY.md), [local stats port](../stats/README.md), [mechanics artifact topology](../mechanics/ARTIFACT_TOPOLOGY.md), [decision records](../docs/decisions/README.md) |
| Windows bridge | `aoa.ps1`, `aoa-doctor-win.ps1`, `aoa-bootstrap-wsl.ps1` | [machine-fit windows bridge](../mechanics/machine-fit/parts/windows-bridge/README.md) |

## Contract

- Keep command names stable unless the route cards, docs, validators, and
  deployment sync behavior move with the change.
- Keep thin wrappers and part-local backend paths aligned; `validate_stack.py`
  treats this bridge as a required topology contract.
- Keep source checkout and deployed runtime paths distinct.
- Keep `aoa-routing-canary` non-canonical: isolated and live-canary
  materialization require exact trust inputs, existing targets require a
  rollback root, and rollback preserves the displaced candidate.
- Keep `aoa-routing-cutover` receipt-bound: it accepts only an exact
  `runtime` trust verdict, public-release record, materialized owner-switch
  receipt, named host change, and atomic predecessor rollback root. It never
  authorizes repository archival.
- Use `aoa-install-systemd --all-user-units` when the deployed Configs mirror
  should become the source path for every allowlisted working user unit without
  restarting those services.
- Use `aoa-install-systemd --provision-mcp-http-auth` as the explicit,
  non-printing secret action before starting authenticated shared MCP owners.
- Use `aoa-install-systemd --rotate-abyss-stack-mcp-auth` only as a standalone
  stopped-unit transaction; it leaves consumer refresh and canary restart
  explicit.
- Use `aoa-install-systemd --system-units` only through `pkexec` or an
  equivalent privileged route, and only for the allowlisted support units under
  `systemd/system/managed-units.txt`.
- Keep wrappers public-safe and avoid printing secrets.
- Keep decision-record shape, indexing, and generated decision graph validated through
  `generate_decision_indexes.py --check` and `validate_decision_records.py`
  when `docs/decisions/` changes.
- Use `python scripts/build_workspace_decision_graph.py --write` to refresh
  the ignored local workspace graph under `Logs/decision-graph/latest/` when an
  agent needs cross-repo decision nodes and edges.
- Use `python scripts/build_workspace_decision_graph.py --check` to fail fast
  when that local workspace graph is stale.
- Use `python scripts/validate_workspace_decision_graph.py` to validate the
  workspace graph schema, JSONL parity, counts, local cache freshness, repo
  source-posture projection, and coverage contract. This route does not fetch
  remotes or prove remote freshness.
- Keep lane command sequences in
  `docs/validation/validation_lanes.json`; `ci_gate.py` and `release_check.py`
  read that manifest instead of owning duplicate command lists.
- Keep the complete pytest selection behind `run_pytest_lane.py`: automatic
  mode uses at most four process-isolated workers over 32 file-aware shards,
  proves their exact disjoint union against one baseline collection, and
  supports exact serial rollback through `ABYSS_STACK_TEST_SCHEDULER=serial`.
  Failed shard logs are replayed at aggregate closeout for bounded-log
  diagnostics; tests are not retried.
- Keep `validate_local_stats_port.py` as a thin delegation to the `aoa-stats`
  contract owner; do not copy the central schemas or validator into this repo.
- Put mechanic-specific implementation logic under the owning
  `mechanics/<package>/parts/<part>/` route when it can move without breaking
  operator command stability.

See [AGENTS.md](AGENTS.md) for editing rules.

`release_check.py` uses synthetic Configs parity by default so source release
audits do not depend on the current machine's live runtime mirror. Use
`python scripts/release_check.py --parity-mode live` only when deliberately
checking `/srv/AbyssOS/abyss-stack/Configs`.
