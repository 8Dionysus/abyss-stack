# AGENTS Rules for coding agents and maintainers working in `config-templates/`.

## Scope
This directory stores public-safe runtime config templates that are bootstrapped into the deployed runtime tree. These are not the live runtime files themselves.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.
## Directory contract
- `Configs/` mirrors `${AOA_STACK_ROOT}/Configs`.
- `Services/` mirrors `${AOA_STACK_ROOT}/Services`.
- `scripts/aoa-bootstrap-configs` copies these trees into the deployed runtime. Keep structure compatible with that contract.
- Current template families include monitoring, TTS, Ollama, and `Services/litellm`.

## Bootstrap route

When an operator explicitly wants to copy public-safe templates into the
deployed runtime tree, use:

Validation is on-demand: use [VALIDATION.md](../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For verification or rehearsals, prefer the temporary-root route below before
touching the deployed runtime.

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

## Hard no
- do not treat bootstrapped runtime copies as source-managed truth
- do not place live secrets in templates
- do not change mounted file paths without updating compose, checks, and docs
- do not commit rendered runtime output or other generated local material
