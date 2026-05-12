# AGENTS Rules for coding agents and maintainers working in `env/`.

## Scope
This directory contains public-safe env examples only. It does not contain live runtime secrets.

## Read before editing
1. `env/README.md`
2. `mechanics/config-projection/docs/SECRETS_BOOTSTRAP.md`
3. `docs/PATHS.md`
4. `docs/STORAGE_LAYOUT.md`

## Directory contract
- Files here are examples and must stay public-safe.
- Real secret-bearing files belong under `/srv/AbyssOS/abyss-stack/Secrets/Configs`, except `stack.env`, which is expected at `/srv/AbyssOS/abyss-stack/Configs/stack.env` and is recommended to be a symlink to `/srv/AbyssOS/abyss-stack/Secrets/Configs/stack.env`.
- Keep the filename mapping stable:
  - `env/stack.env.example` -> `${AOA_STACK_ROOT}/Configs/stack.env`
  - `env/langchain-api.env.example` -> `${AOA_STACK_ROOT}/Secrets/Configs/langchain-api.env`
  - `env/ovms-api.env.example` -> `${AOA_STACK_ROOT}/Secrets/Configs/ovms-api.env`
  - `env/tos-graph.env.example` -> `${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env`

## Editing rules
- Use names and obviously fake placeholders such as `CHANGE_ME`.
- Never commit plausible live values, real API keys, or environment-specific hostnames.
- Prefer comments that explain purpose, path, and expected shape.
- Keep examples aligned with what compose and runtime services actually consume.
- Add new example files only when there is a real runtime file contract behind them. Use the `.example` suffix.

## When adding or changing variables
- Update the consuming compose module or service config if the contract changes.
- Update `mechanics/config-projection/docs/SECRETS_BOOTSTRAP.md` if the change affects secret bootstrap.
- Update `scripts/aoa-check-layout` if a new secret-bearing file becomes required.
- Update `scripts/validate_stack.py` if the file should be treated as required project structure.

## Verify
```bash
python scripts/validate_stack.py
scripts/aoa-first-run --strict
scripts/aoa-check-layout --ignore-secrets
```

If the example set changed, re-read `mechanics/config-projection/docs/SECRETS_BOOTSTRAP.md` and confirm the bootstrap instructions still match.

## Hard no
- do not commit live `.env` files
- do not place real secrets in comments, examples, screenshots, or logs
- do not create example files that have no runtime consumer
- do not drift away from the canonical `/srv/AbyssOS/abyss-stack` and `Secrets/Configs` mapping
