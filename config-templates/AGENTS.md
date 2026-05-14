# AGENTS Rules for coding agents and maintainers working in `config-templates/`.

## Scope
This directory stores public-safe runtime config templates that are bootstrapped into the deployed runtime tree. These are not the live runtime files themselves.

## Read before editing
1. `config-templates/README.md`
2. `docs/install/DEPLOYMENT.md`
3. `docs/runtime/STORAGE_LAYOUT.md`
4. `mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md`
5. `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`

## Directory contract
- `Configs/` mirrors `${AOA_STACK_ROOT}/Configs`.
- `Services/` mirrors `${AOA_STACK_ROOT}/Services`.
- `scripts/aoa-bootstrap-configs` copies these trees into the deployed runtime. Keep structure compatible with that contract.
- Current template families include monitoring, TTS, Ollama, and `Services/litellm`.

## Template rules
- Stay public-safe. No real secrets, private tokens, or machine-specific hostnames belong here.
- Use Linux runtime paths and container-local paths, not source-checkout paths.
- Keep filenames and mount paths aligned with compose modules and `scripts/aoa-check-layout`.
- Prefer sane defaults and placeholders over environment-specific tuning.
- If a setting becomes secret-bearing, move the sensitive part to the env and secrets contract instead of sneaking secrets into a template.

## When adding or changing templates
- Update the consuming compose module if a path, filename, or mount contract changes.
- Update `scripts/aoa-check-layout` if the file becomes part of the required runtime shape.
- Update `scripts/aoa-install-layout` if new runtime directories are needed before bootstrap or by mounted state.
- Update `config-templates/README.md` and the relevant docs when the operating contract changes.
- If you introduce a new top-level tree beyond `Configs/` or `Services/`, update `scripts/aoa-bootstrap-configs`.

`Configs/agent-api/return-policy.yaml` is public-safe runtime policy, not a secret-bearing env file.

## Verify
Use a temporary runtime root you control:
```bash
export AOA_STACK_ROOT=/tmp/abyss-stack-test
export AOA_CONFIGS_ROOT=/tmp/abyss-stack-test/Configs
scripts/aoa-install-layout
scripts/aoa-bootstrap-configs --force
scripts/aoa-check-layout --ignore-secrets
python scripts/validate_stack.py
```

## Hard no
- do not treat bootstrapped runtime copies as source-managed truth
- do not place live secrets in templates
- do not change mounted file paths without updating compose, checks, and docs
- do not commit rendered runtime output or other generated local material
