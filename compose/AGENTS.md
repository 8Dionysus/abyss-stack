# AGENTS Rules for coding agents and maintainers working in `compose/`.

## Scope
This directory owns compose-time runtime shape: atomic modules, profile expansion, preset expansion, and optional tuning overlays.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.
## Directory contract
- `modules/*.yml` are the atomic runtime pieces.
- `profiles/*.txt` list module filenames in activation order.
- `presets/*.txt` list profile names in activation order.
- `tuning/*.yml` are optional overlays. Do not promote a tuning overlay into the default operating contract by accident.
- `44-llamacpp-agent-sidecar.yml` is a pilot sidecar, not a normal profile
  member.

## Composition rules
- Prefer a new small module over swelling an unrelated existing module.
- Preserve the numeric layer story unless there is a deliberate redesign:
  - `10-*` storage
  - `20-*` orchestration
  - `30-*` and `31-*` inference
  - `40-*`, `41-*`, and `42-*` gateway and agent overlays
  - `50-*` and `51-*` helper tooling
  - `60-*` observability
- Keep profiles and presets as plain ordered lists. Comments and blank lines are fine; hidden logic is not.
- Use Linux runtime paths and the canonical env-driven roots such as `${AOA_STACK_ROOT:-/srv/AbyssOS/abyss-stack}`. Do not bake source-checkout paths or Windows host paths into compose.
- Keep host exposure local-first. Host-published ports stay on `127.0.0.1` unless an operator-facing redesign explicitly says otherwise.
- Prefer `expose` or internal-only health and probe patterns for services that should stay private.
- Do not put real secrets, tokens, or live values into compose files. Reference runtime files under `Configs/` and `Secrets/` instead.

## When changing modules
- If a module structurally depends on another module, update
  `scripts/validators/profile_topology.py` `MODULE_REQUIREMENTS`.
- If a module adds or changes host-facing endpoints, update:
  - `scripts/aoa-profile-endpoints`
  - `scripts/aoa-smoke`
  - `docs/profiles/PROFILE_RECIPES.md`
- If a module adds or changes internal-only surfaces, update:
  - `scripts/aoa-internal-probes`
  - `mechanics/runtime-lifecycle/parts/wait-smoke/docs/INTERNAL_PROBES.md`
- If a module needs new runtime config files, update `config-templates/`, `scripts/aoa-check-layout`, and the relevant docs.
- If a module needs new runtime directories or mounts, update `scripts/aoa-install-layout` and the relevant docs.
- If `41-agent-api.yml` or a successor runtime service gains a return-policy mount or return-log path, update `config-templates/`, `scripts/aoa-check-layout`, `scripts/aoa-install-layout`, and the relevant docs together.

## When changing profiles or presets
- Keep activation order meaningful and minimal.
- Update `compose/README.md` and `docs/profiles/PRESETS.md` or `docs/profiles/PROFILE_RECIPES.md` when the operating contract changes.
- If a new preset becomes first-class, add or adjust rehearsal coverage in `.github/workflows/validate-stack.yml`.

## Verify
Run the smallest set that proves the change:
Validation is on-demand: use [VALIDATION.md](../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For preset work, use the matching preset form instead of only testing profiles. Treat rendered config as potentially secret-bearing.

## Hard no
- do not collapse the stack back into one giant compose file
- do not widen host exposure from `127.0.0.1` without explicit operator intent
- do not turn internal-only services into host-facing defaults by accident
- do not reintroduce legacy pre-`/srv/AbyssOS/abyss-stack` paths
- do not let profiles or presets drift away from the docs and probe scripts
