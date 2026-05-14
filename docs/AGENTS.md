# AGENTS.md

Local guidance for root `docs/` in `abyss-stack`. Read the root `AGENTS.md`
first.

## Scope

This directory owns repo-wide operator and source-checkout documentation. Its
districts separate route contracts, runtime topology, install flow, operations,
profiles, governance, decisions, and preserved legacy references.

Root-level system and agent-surface design live at `DESIGN.md` and
`DESIGN.AGENTS.md`, not under `docs/`.

Entry route-mode law lives at `docs/routes/START_HERE_ROUTE_CONTRACT.md`.

Mechanic-owned runtime doctrine belongs under `mechanics/<package>/docs/` or a
more specific `mechanics/<package>/parts/<part>/docs/` surface.

## Local Contract

- Keep `docs/README.md` as the short index for this directory.
- Keep each immediate child district as a coherent owner lane:
  `routes/`, `runtime/`, `install/`, `operations/`, `profiles/`,
  `governance/`, `decisions/`, and `legacy/`.
- Keep `docs/routes/START_HERE_ROUTE_CONTRACT.md` as the route-mode contract
  for root entry surfaces.
- Keep root docs as entrypoints for the whole repository, not as a flat
  dumping ground for package-owned mechanics.
- Do not duplicate mechanic-owned doctrine here once a package-local canonical
  home exists.
- Keep decision records under `docs/decisions/`; follow
  `docs/decisions/AGENTS.md` and `docs/decisions/TEMPLATE.md` for durable
  decision rationale.
- Keep old root guidance or old-stack migration material under `docs/legacy/`
  with an explicit active-route bridge.
- If a root doc routes to package docs, link to the package-local source rather
  than copying its content.

## Validate

Use the root validation path after documentation topology changes:

```bash
python scripts/validate_decision_records.py
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python -m pytest tests/test_roadmap_parity.py tests/test_decision_records.py tests/test_validate_stack_required_files.py
```
