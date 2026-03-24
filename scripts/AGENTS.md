# AGENTS Rules for coding agents and maintainers working in `scripts/`.

## Scope
This directory owns the runtime bridge, bootstrap helpers, introspection helpers, lifecycle wrappers, probes, and repository validation helpers for `abyss-stack`.

## Read before editing
1. `scripts/aoa-lib.sh`
2. `.github/workflows/validate-stack.yml`
3. `docs/FIRST_RUN.md`
4. `docs/DOCTOR.md`
5. `docs/DEPLOYMENT.md`
6. `docs/PRESETS.md`
7. `docs/PROFILE_RECIPES.md`
8. `docs/RENDER_TRUTH.md`
9. `docs/INTERNAL_PROBES.md`
10. `docs/PATHS.md`

## Directory contract
- Bash wrappers are operator-facing helpers and should be safe by default.
- Shared env defaults, selector parsing, compose resolution, and probe helpers live in `scripts/aoa-lib.sh`.
- `scripts/validate_stack.py` is the repo-structure validator. Keep it stdlib-only unless the repo explicitly changes policy.

## Shell script rules
- Use `#!/usr/bin/env bash` and `set -euo pipefail`.
- Source `aoa-lib.sh` instead of reimplementing defaults or selector parsing.
- Preserve selector semantics across related tools: `--preset`, `--profile`, repeated flags, comma-separated forms, and `--` pass-through where applicable.
- Prefer additive, explicit flags for risky actions. `--delete`, `--force`, `--enable-now`, and `--with-internal` are the model.
- Keep output operator-legible. Never print secret values or dump secret-bearing files.

## Runtime contract rules
- Keep the canonical defaults from `aoa-lib.sh`:
  - `AOA_STACK_ROOT=/srv/abyss-stack`
  - `AOA_CONFIGS_ROOT=${AOA_STACK_ROOT}/Configs`
  - `AOA_VAULT_ROOT=/abyss`
  - default profile `core`
- Keep the distinction between source checkout and deployed runtime explicit. Bridge with `aoa-sync-configs` and `aoa-bootstrap-configs`; do not blur them.
- Do not reintroduce legacy pre-`/srv/abyss-stack` paths. `validate_stack.py` intentionally guards against that drift.

## Cross-file duties
- If you change layout or bootstrap expectations, update `aoa-install-layout`, `aoa-sync-configs`, `aoa-bootstrap-configs`, `aoa-check-layout`, and the relevant docs as one change.
- If you change compose selection or endpoint expectations, keep `aoa-doctor`, `aoa-profile-modules`, `aoa-profile-endpoints`, `aoa-render-services`, `aoa-render-config`, `aoa-smoke`, and `aoa-internal-probes` aligned.
- If you add a first-class script, update:
  - `scripts/validate_stack.py`
  - `.github/workflows/validate-stack.yml`
  - the relevant docs in `docs/`
- If you introduce or remove required runtime files, update both `aoa-check-layout` and `validate_stack.py`.

## Verify
For shell work, run the smallest useful set:
```bash
python scripts/validate_stack.py
shellcheck scripts/aoa-lib.sh scripts/<touched-script>
bash -n scripts/<touched-script>
```

For bootstrap or lifecycle changes, rehearse the flow encoded in `.github/workflows/validate-stack.yml` with a temporary runtime root.

## Hard no
- do not make read-only introspection helpers mutate runtime state
- do not leak secrets through stdout, stderr, or committed fixtures
- do not hardcode source-checkout paths into deployed-runtime commands
- do not let probe scripts and docs disagree about endpoints
