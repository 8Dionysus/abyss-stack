# AGENTS.md

Local guidance for `.agents/skills/` in `abyss-stack`. Read the root
`AGENTS.md` first.

## Scope

This directory is the repo-local skill install and overlay surface. Most entries
are symlinks into the stronger `aoa-skills` owner; local directories exist only
when `abyss-stack` needs a portable overlay tied to stack runtime contracts.

## Local Contract

- Do not move canonical skill law into this repository.
- Keep symlinked skill names aligned with the stronger `aoa-skills` source.
- Keep local overlays thin, source-safe, and explicit about their canonical
  upstream.
- When an overlay references stack surfaces, point to package-local mechanics
  paths rather than old root topology.

## Validate

Use the root nested guidance check after touching skill surfaces:

```bash
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```
