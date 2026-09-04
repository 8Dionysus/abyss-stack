# AGENTS Rules for coding agents and maintainers working in `scripts/`.

## Scope
This directory owns the runtime bridge, bootstrap helpers, introspection helpers, lifecycle wrappers, probes, and repository validation helpers for `abyss-stack`.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; `scripts/README.md` is the semantic route when needed, and entering this subtree does not require an unconditional inventory.

## Directory contract
- Root operator scripts are stable wrappers and should be safe by default.
- Operator implementation bodies live under the owning mechanic parts.
- Shared env defaults, selector parsing, compose resolution, and probe helpers live in `scripts/aoa-lib.sh`.
- `scripts/validate_stack.py` is the repo-structure validator. Keep it stdlib-only unless the repo explicitly changes policy.
- `scripts/validate_stack.py` may parse repo-local quest YAML in the validation workflow. If you touch that path, keep the workflow PyYAML install, validator logic, and questbook tests aligned.
- `scripts/validation_lanes.py` loads
  `docs/validation/validation_lanes.json`. It is a loader/API, not a second
  command list.
- `scripts/ci_gate.py` executes named validation lanes from the manifest.
- `scripts/run_pytest_lane.py` schedules the complete default pytest selection.
  It bounds file-aware work stealing to four process-isolated workers and proves
  baseline/assignment/observed-selection parity; it does not own test selection.
  It replays failed shard logs at aggregate closeout without retrying tests.
- `scripts/validate_local_stats_port.py` delegates the local port contract to
  the `aoa-stats` validator and does not own shared measurement semantics.
- `scripts/release_check.py` remains the release entrypoint and Configs parity
  stabilizer, but its release command sequence comes from the lane manifest.
- `scripts/decision_indexes.py` and `scripts/generate_decision_indexes.py`
  own generated decision-index read models. Keep them stdlib-only and aligned
  with `docs/decisions/`.
- `scripts/validate_decision_records.py` is the decision-rationale shape and
  index validator. Keep it stdlib-only and aligned with `docs/decisions/`.
- `scripts/aoa-host-facts` routes to `mechanics/machine-fit/parts/host-facts/aoa_host_facts.py`. Keep it stdlib-only and secret-safe.
- `scripts/aoa-machine-bridge` routes to `mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py`. Keep it stdlib-only, secret-safe, and non-mutating toward the host.
- `scripts/aoa-machine-fit` routes to `mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py`. Keep it stdlib-only and secret-safe.
- `scripts/aoa-diagnose` routes through `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.sh` into the diagnostic Python backend. Keep it stdlib-only and citation-friendly.
- `scripts/aoa-qwen-run` routes to `mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py`. Keep it stdlib-only and local-only.
- `scripts/aoa-long-horizon-pilot` and `scripts/aoa-bounded-autonomy-pilot`
  are quiet operator bridges into package-local archived pilot runners.
  Keep the bridge names stable unless the package route changes too.

## Shell script rules
- Use `#!/usr/bin/env bash` and `set -euo pipefail`.
- Source `aoa-lib.sh` instead of reimplementing defaults or selector parsing.
- Preserve selector semantics across related tools: `--preset`, `--profile`, repeated flags, comma-separated forms, and `--` pass-through where applicable.
- Prefer additive, explicit flags for risky actions. `--delete`, `--force`, `--enable-now`, and `--with-internal` are the model.
- Keep output operator-legible. Never print secret values or dump secret-bearing files.

## Runtime contract rules
- Keep the canonical defaults from `aoa-lib.sh`:
  - `AOA_STACK_ROOT=/srv/AbyssOS/abyss-stack`
  - `AOA_CONFIGS_ROOT=${AOA_STACK_ROOT}/Configs`
  - `AOA_VAULT_ROOT=/abyss`
  - default profile `substrate`
- Keep the distinction between source checkout and deployed runtime explicit. Bridge with `aoa-sync-configs` and `aoa-bootstrap-configs`; do not blur them.
- Do not reintroduce stale pre-`/srv/AbyssOS/abyss-stack` paths. `validate_stack.py` intentionally guards against that drift.

## Cross-file duties
- If you change layout or bootstrap expectations, update `aoa-install-layout`, `aoa-sync-configs`, `aoa-bootstrap-configs`, `aoa-check-layout`, and the relevant docs as one change.
- If you change compose selection or endpoint expectations, keep `aoa-doctor`, `aoa-profile-modules`, `aoa-profile-endpoints`, `aoa-render-services`, `aoa-render-config`, `aoa-smoke`, and `aoa-internal-probes` aligned.
- If you add a first-class script, update:
  - `scripts/validate_stack.py`
  - `.github/workflows/validate-stack.yml`
  - `docs/validation/script_inventory.json`
  - the relevant docs in `docs/`
- If you change validation lane commands, update
  `docs/validation/validation_lanes.json`, `docs/validation/COMMAND_AUTHORITY.md`,
  and the focused command-authority tests instead of copying commands into
  workflow YAML or `release_check.py`.
- If you introduce or remove required runtime files, update both `aoa-check-layout` and `validate_stack.py`.
- If you change host-facts shape or capture destinations, update `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`, `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md`, `mechanics/machine-fit/parts/host-facts/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If you change machine-bridge shape or capture destinations, update `mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md`, `mechanics/machine-fit/parts/machine-bridge/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If you change machine-fit shape or capture destinations, update `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`, `mechanics/machine-fit/parts/fit-record/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If the runtime wrapper consumes a return-policy file or writes return-event bundles, keep those contracts explicit in docs, layout checks, and render-truth guidance.

## Verify
For shell work, use the smallest useful set from [VALIDATION.md](../VALIDATION.md).

For bootstrap or lifecycle changes, rehearse the flow encoded in `.github/workflows/validate-stack.yml` with a temporary runtime root.

## Hard no
- do not make read-only introspection helpers mutate runtime state
- do not leak secrets through stdout, stderr, or committed fixtures
- do not hardcode source-checkout paths into deployed-runtime commands
- do not let probe scripts and docs disagree about endpoints
