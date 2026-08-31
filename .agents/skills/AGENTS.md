# AGENTS.md

Local guidance for `.agents/skills/` in `abyss-stack`. Read the root
`AGENTS.md` first.

## Scope

This directory is the transitional repo-local projection of shared skills.
Entries are symlinks or checkout-safe pointer files into the stronger
`aoa-skills` owner. Canonical `abyss-stack` procedures live under root
`skills/` and are exposed through the OS user profile, not duplicated here.
In this workspace, each entry targets
`/srv/AbyssOS/aoa-skills/.agents/skills/<skill-name>`. A symlink is used when
that owner path is present; otherwise a regular pointer file preserves the
owner coordinate so a clean checkout and an external actor projection retain
the required surface without copying canonical content. Older flat sibling
targets are historical drift, not an active route.

## Local Contract

- Do not move shared skill law into this repository.
- Do not place stack-owned canonical packages or same-name global copies here.
- Keep projected skill names aligned with the stronger `aoa-skills` source.
- Keep symlink targets and pointer-file contents under
  `/srv/AbyssOS/aoa-skills/.agents/skills/`.
- Treat this projection as compatibility state until the global OS profile
  preserves the shared functions without repository duplicates.

## Validate

After touching skill surfaces, use the root nested guidance check from [VALIDATION.md](../../VALIDATION.md).
