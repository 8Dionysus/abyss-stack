# AGENTS Rules for coding agents and maintainers working in `scripts/`.

## Scope
This directory owns the runtime bridge, bootstrap helpers, introspection helpers, lifecycle wrappers, probes, and repository validation helpers for `abyss-stack`.

## Read before editing
1. `scripts/aoa-lib.sh`
2. `.github/workflows/validate-stack.yml` in the source checkout only; the runtime `Configs/` mirror does not include `.github/`
3. `docs/FIRST_RUN.md`
4. `mechanics/diagnostic-spine/docs/DOCTOR.md`
5. `docs/DEPLOYMENT.md`
6. `docs/PRESETS.md`
7. `docs/PROFILE_RECIPES.md`
8. `mechanics/config-projection/docs/RENDER_TRUTH.md`
9. `mechanics/runtime-lifecycle/docs/INTERNAL_PROBES.md`
10. `mechanics/governed-execution/docs/RECURRENCE_RUNTIME_POLICY.md`
11. `docs/PATHS.md`
12. `mechanics/machine-fit/docs/REFERENCE_PLATFORM.md`
13. `mechanics/machine-fit/docs/REFERENCE_PLATFORM_SPEC.md`
14. `mechanics/machine-fit/docs/MACHINE_FIT_POLICY.md`
15. `mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md`

## Directory contract
- Bash wrappers are operator-facing helpers and should be safe by default.
- Shared env defaults, selector parsing, compose resolution, and probe helpers live in `scripts/aoa-lib.sh`.
- `scripts/validate_stack.py` is the repo-structure validator. Keep it stdlib-only unless the repo explicitly changes policy.
- `scripts/validate_stack.py` may parse repo-local quest YAML in the validation workflow. If you touch that path, keep the workflow PyYAML install, validator logic, and questbook tests aligned.
- `scripts/aoa-host-facts` owns durable machine-readable host-facts capture. Keep it stdlib-only and secret-safe.
- `scripts/aoa-machine-bridge` owns the stack-side read-only consumer record for `abyss-machine`. Keep it stdlib-only, secret-safe, and non-mutating toward the host.
- `scripts/aoa-machine-fit` owns the durable bounded record of what the current machine should prefer right now. Keep it stdlib-only and secret-safe.
- `scripts/aoa-diagnose` owns the read-only runtime diagnostic spine collector, runtime-owned diagnosis companions, explicit `last_good` anchor promotion, explicit `reviewed_diagnosis_ref` bridge writing, and runtime-owned repair handoff artifacts. Keep it stdlib-only and citation-friendly.
- `scripts/aoa-qwen-run` is the generic bounded prompt runner for `langchain-api /run`. Keep it stdlib-only and local-only.
- `scripts/aoa-long-horizon-pilot` and `scripts/aoa-bounded-autonomy-pilot`
  are quiet operator bridges into package-local preserved W5/W6 pilot runners.
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
- Do not reintroduce legacy pre-`/srv/AbyssOS/abyss-stack` paths. `validate_stack.py` intentionally guards against that drift.

## Cross-file duties
- If you change layout or bootstrap expectations, update `aoa-install-layout`, `aoa-sync-configs`, `aoa-bootstrap-configs`, `aoa-check-layout`, and the relevant docs as one change.
- If you change compose selection or endpoint expectations, keep `aoa-doctor`, `aoa-profile-modules`, `aoa-profile-endpoints`, `aoa-render-services`, `aoa-render-config`, `aoa-smoke`, and `aoa-internal-probes` aligned.
- If you add a first-class script, update:
  - `scripts/validate_stack.py`
  - `.github/workflows/validate-stack.yml`
  - the relevant docs in `docs/`
- If you introduce or remove required runtime files, update both `aoa-check-layout` and `validate_stack.py`.
- If you change host-facts shape or capture destinations, update `mechanics/machine-fit/docs/REFERENCE_PLATFORM.md`, `mechanics/machine-fit/docs/REFERENCE_PLATFORM_SPEC.md`, `mechanics/machine-fit/parts/host-facts/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If you change machine-bridge shape or capture destinations, update `mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md`, `mechanics/machine-fit/parts/machine-bridge/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If you change machine-fit shape or capture destinations, update `mechanics/machine-fit/docs/MACHINE_FIT_POLICY.md`, `mechanics/machine-fit/parts/fit-record/`, `scripts/validate_stack.py`, and `.github/workflows/validate-stack.yml` in the same change.
- If the runtime wrapper consumes a return-policy file or writes return-event bundles, keep those contracts explicit in docs, layout checks, and render-truth guidance.

## Verify
For shell work, run the smallest useful set:
```bash
python scripts/validate_stack.py
python -m py_compile scripts/validate_stack.py mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py scripts/aoa-host-facts scripts/aoa-machine-bridge scripts/aoa-machine-fit scripts/aoa-qwen-run
shellcheck scripts/aoa-lib.sh scripts/aoa-diagnose scripts/<touched-script>
bash -n scripts/<touched-script>
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
