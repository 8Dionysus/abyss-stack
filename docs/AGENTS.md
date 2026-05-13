# AGENTS.md

Local guidance for root `docs/` in `abyss-stack`. Read the root `AGENTS.md`
first.

## Scope

This directory owns repo-wide operator and source-checkout documentation:
architecture, deployment, first-run, lifecycle, storage, security, release,
branch policy, migration notes, questbook integration, and decision records.

Root-level system and agent-surface design live at `DESIGN.md` and
`DESIGN.AGENTS.md`, not under `docs/`.

Mechanic-owned runtime doctrine belongs under `mechanics/<package>/docs/` or a
more specific `mechanics/<package>/parts/<part>/docs/` surface.

## Local Contract

- Keep `docs/README.md` as the short index for this directory.
- Keep root docs as entrypoints for the whole repository, not as a flat dumping
  ground for package-owned mechanics.
- Do not duplicate mechanic-owned doctrine here once a package-local canonical
  home exists.
- Keep decision records under `docs/decisions/`.
- If a root doc routes to package docs, link to the package-local source rather
  than copying its content.

## Validate

Use the root validation path after documentation topology changes:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python -m pytest tests/test_roadmap_parity.py tests/test_validate_stack_required_files.py
```
