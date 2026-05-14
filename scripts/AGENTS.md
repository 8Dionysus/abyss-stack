# AGENTS Rules for coding agents and maintainers working in `scripts/`.

## Scope
This directory owns the runtime bridge, bootstrap helpers, introspection helpers, lifecycle wrappers, probes, and repository validation helpers for `abyss-stack`.

## Read before editing
1. `scripts/aoa-lib.sh`
2. `scripts/README.md`
3. `.github/workflows/validate-stack.yml` in the source checkout only; the runtime `Configs/` mirror does not include `.github/`
4. `docs/install/FIRST_RUN.md`
5. `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`
6. `docs/install/DEPLOYMENT.md`
7. `docs/profiles/PRESETS.md`
8. `docs/profiles/PROFILE_RECIPES.md`
9. `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`
10. `mechanics/runtime-lifecycle/parts/wait-smoke/docs/INTERNAL_PROBES.md`
11. `mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md`
12. `docs/runtime/PATHS.md`
13. `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`
14. `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md`
15. `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`
16. `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`

## Directory contract
- Root operator scripts are stable wrappers and should be safe by default.
- Operator implementation bodies live under the owning mechanic parts.
- Shared env defaults, selector parsing, compose resolution, and probe helpers live in `scripts/aoa-lib.sh`.
- `scripts/validate_stack.py` is the repo-structure validator. Keep it stdlib-only unless the repo explicitly changes policy.
- `scripts/validate_stack.py` may parse repo-local quest YAML in the validation workflow. If you touch that path, keep the workflow PyYAML install, validator logic, and questbook tests aligned.
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
  - default profile `core`
- Keep the distinction between source checkout and deployed runtime explicit. Bridge with `aoa-sync-configs` and `aoa-bootstrap-configs`; do not blur them.
- Do not reintroduce stale pre-`/srv/AbyssOS/abyss-stack` paths. `validate_stack.py` intentionally guards against that drift.

## Cross-file duties
- If you change layout or bootstrap expectations, update `aoa-install-layout`, `aoa-sync-configs`, `aoa-bootstrap-configs`, `aoa-check-layout`, and the relevant docs as one change.
- If you change compose selection or endpoint expectations, keep `aoa-doctor`, `aoa-profile-modules`, `aoa-profile-endpoints`, `aoa-render-services`, `aoa-render-config`, `aoa-smoke`, and `aoa-internal-probes` aligned.
- If you add a first-class script, update:
  - `scripts/validate_stack.py`
  - `.github/workflows/validate-stack.yml`
  - the relevant docs in `docs/`
- If you introduce or remove required runtime files, update both `aoa-check-layout` and `validate_stack.py`.
- If you change host-facts shape or capture destinations, update `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`, `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md`, `mechanics/machine-fit/parts/host-facts/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If you change machine-bridge shape or capture destinations, update `mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md`, `mechanics/machine-fit/parts/machine-bridge/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If you change machine-fit shape or capture destinations, update `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`, `mechanics/machine-fit/parts/fit-record/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If the runtime wrapper consumes a return-policy file or writes return-event bundles, keep those contracts explicit in docs, layout checks, and render-truth guidance.

## Verify
For shell work, run the smallest useful set:
```bash
python scripts/validate_stack.py
python scripts/validate_decision_records.py
python -m py_compile scripts/validate_stack.py mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py mechanics/machine-fit/parts/host-facts/aoa_host_facts.py mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py
shellcheck scripts/aoa-lib.sh scripts/aoa-diagnose scripts/<touched-script>
shellcheck scripts/aoa-lib.sh mechanics/<package>/parts/<part>/<touched-backend>.sh
bash -n scripts/<touched-script> mechanics/<package>/parts/<part>/<touched-backend>.sh
scripts/aoa-host-facts --mode public
scripts/aoa-machine-bridge --mode public --write /tmp/machine-bridge.public.review.json
scripts/aoa-machine-fit --mode public
```

For bootstrap or lifecycle changes, rehearse the flow encoded in `.github/workflows/validate-stack.yml` with a temporary runtime root.

## Hard no
- do not make read-only introspection helpers mutate runtime state
- do not leak secrets through stdout, stderr, or committed fixtures
- do not hardcode source-checkout paths into deployed-runtime commands
- do not let probe scripts and docs disagree about endpoints
