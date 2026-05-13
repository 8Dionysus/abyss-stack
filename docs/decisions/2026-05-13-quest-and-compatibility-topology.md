# 2026-05-13 Quest And Compatibility Topology

## Status

Accepted.

## Context

The remaining topology cleanup had three related failure modes:

- root quest records were still flat files under `quests/`
- inference-pilot compatibility IDs were still easy to spread through active
  pilot code
- federation seams needed to keep upstream eval and playbook names without
  making those names local topology

The donor pattern from `Agents-of-Abyss` showed that quest records should be
lane/state source files with generated read models, not top-level aliases. The
same pass also showed that legacy names are not trash: they need a clear
compatibility or provenance home.

## Decision

Use lane/state quest source paths under `quests/<lane>/<state>/` and keep
`QUESTBOOK.md` as the compact index.

Move quest route and read-model construction into
`quests/scripts/quest_surface.py`, with `scripts/validate_stack.py` remaining
the repo-wide orchestrator.

Keep preserved local-trials wire IDs behind
`mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py`, and
have active LangGraph and llama.cpp pilots call the adapter by role.

Record upstream eval/playbook compatibility names in
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.
Active local docs should use clean route names; route-api and tests may keep
upstream names only where they prove compatibility behavior.

## Consequences

- Future quest records have an owner lane and lifecycle state before they
  become generated examples or dispatch entries.
- Top-level quest aliases are intentionally invalid.
- Active pilot code no longer needs to spell preserved gate IDs directly.
- Upstream contract names remain visible without becoming local naming law.
- The root validator stays as the public check, but package-owned helpers now
  hold the owner-local route rules they can reasonably own.
