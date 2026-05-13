# Quest District

This directory holds tracked `abyss-stack` obligations that should survive the
current diff.

It is not a private scratchpad and not a second roadmap. Program direction
belongs in [ROADMAP.md](../ROADMAP.md). The compact root quest index is
[QUESTBOOK.md](../QUESTBOOK.md).

## Source Surfaces

- `*/<state>/ABYSS-STACK-Q-*.yaml` are active quest source records.
- `schemas/` defines the local quest and dispatch contracts.
- `examples/` carries public-safe catalog and dispatch examples derived from the
  active quest records.
- `scripts/quest_surface.py` owns the lane/state route table and expected
  catalog/dispatch read-model shape.
- `scripts/build_quest_examples.py` rebuilds or checks those derived examples.

Quest source placement is lane-first and lifecycle-state-first. Top-level
`ABYSS-STACK-Q-*` aliases are intentionally absent; route directly to
`quests/<lane>/<state>/ABYSS-STACK-Q-*`.
The root validator imports the owner-local quest helper instead of carrying
quest topology as root-only validator state.

## Lanes

| Lane | Use |
|---|---|
| [`stack/`](stack/README.md) | repo-wide stack and guardrail obligations |
| [`profiles/`](profiles/README.md) | profile, preset, and rollout obligations |
| [`machine-fit/`](machine-fit/README.md) | platform adaptation and host-fit follow-through |
| [`rpg-runtime/`](rpg-runtime/README.md) | RPG runtime service and projection obligations |
| [`diagnostics/`](diagnostics/README.md) | diagnostic spine and repair-handoff obligations |
| [`tos-graph/`](tos-graph/README.md) | ToS graph helper rollout obligations |

## Lifecycle States

Each lane may contain:

| State | Use |
|---|---|
| `captured/` | public-safe obligation exists, but route shaping is not complete |
| `triaged/` | route-bearing obligation with enough shape to split, promote, or close |
| `ready/` | next owner action is clear and bounded |
| `active/` | currently being advanced by the owner lane |
| `blocked/` | waiting on a named dependency or owner decision |
| `reanchor/` | old route no longer matches; choose a new owner, band, or evidence path |
| `done/` | landed with enough public evidence to leave the active index |
| `dropped/` | intentionally closed without landing, with a visible reason |

## Boundary

Quests here track `abyss-stack` runtime, deployment, lifecycle, platform,
diagnostic, and infrastructure follow-through. They do not author sibling
repository doctrine and do not prove runtime state by themselves.

Historical mechanic quest stubs are routed through the owning mechanic legacy
path so this root district stays current.

## Checks

```bash
python scripts/validate_stack.py
python quests/scripts/build_quest_examples.py --check
python -m pytest tests/test_validate_stack_questbook.py
```
