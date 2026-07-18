# AGENTS.md

Local guidance for `.agents/skills/` in `abyss-stack`. Read the root
`AGENTS.md` first.

## Scope

This directory is the transitional repo-local projection of shared skills.
Entries are symlinks into the stronger `aoa-skills` owner. Canonical
`abyss-stack` procedures live under root `skills/` and are exposed through the
OS user profile, not duplicated here.
In this workspace, symlinked skills target
`/srv/AbyssOS/aoa-skills/.agents/skills/<skill-name>`; older flat sibling
targets are historical drift, not an active route.

## Local Contract

- Do not move shared skill law into this repository.
- Do not place stack-owned canonical packages or same-name global copies here.
- Keep symlinked skill names aligned with the stronger `aoa-skills` source.
- Keep symlink targets under `/srv/AbyssOS/aoa-skills/.agents/skills/`.
- Treat this projection as compatibility state until the global OS profile
  preserves the shared functions without repository duplicates.

## Validate

Use the root nested guidance check after touching skill surfaces:

```bash
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```
