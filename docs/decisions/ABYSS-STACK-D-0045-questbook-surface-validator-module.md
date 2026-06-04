# Questbook Surface Validator Module

- Decision ID: ABYSS-STACK-D-0045
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/questbook_surface.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, questbook, generated read-model
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: federation-seams
- Guard families: validation lane, generated read-model, source topology
- Posture: accepted sixth validator-module split

## Context

The root stack validator carried a large questbook surface check. That check
protects `QUESTBOOK.md`, quest source topology under `quests/<lane>/<state>/`,
generated quest catalog and dispatch examples, and the RPG runtime read-model
schemas/examples that project upstream meaning into stack-owned runtime
collections.

This surface is cohesive but not generic root topology. It is the stack's
quest/read-model boundary: `abyss-stack` may assemble runtime-owned collections
and generated examples, but it must not become upstream meaning authority.

## Options considered

- Keep questbook validation in `scripts/validate_stack.py`.
- Move questbook authority into `quests/scripts/quest_surface.py`.
- Move root validation implementation into a focused validator module while
  preserving root helper compatibility only as a temporary extraction bridge.

## Decision

Move questbook validation implementation into
`scripts/validators/questbook_surface.py`.

During the extraction bridge, root helper compatibility preserved existing
questbook tests and direct callers while moving the implementation out of the
monolith. D-0063 closes that bridge: questbook constants and focused tests now
route directly to `scripts/validators/questbook_surface.py`, while quest source
helpers remain in `quests/scripts/quest_surface.py`.

Add focused unit tests in `tests/test_questbook_validator_module.py` for the
module-level schema-envelope and generated-collection guards.

## Rationale

The questbook block was one of the largest coherent surfaces still inside
`validate_stack.py`. Extracting it reduces the root validator materially while
keeping the current generated quest examples and RPG read-model contracts
unchanged.

The split also keeps `quests/scripts/quest_surface.py` in its current role: it
builds quest source paths and expected generated entries. The validator module
consumes that behavior without absorbing quest-surface generation authority.

## Consequences

- Positive: questbook and RPG read-model validation now have an owner module.
- Positive: existing helper callers stayed stable during the extraction
  bridge.
- Positive: module-level tests cover schema-envelope and generated-collection
  drift.
- Tradeoff: the first slice left quest constants in the root until the later
  owner-constant migration completed.
- Follow-up: future questbook changes should update the focused module and
  tests before widening root validation.

## Source surfaces

- `scripts/validators/questbook_surface.py`
- `scripts/validate_stack.py`
- `quests/`
- `quests/scripts/quest_surface.py`
- `mechanics/federation-seams/parts/rpg-runtime/`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `docs/testing/test_inventory.json`
- `tests/test_questbook_validator_module.py`
- `tests/test_questbook_surface_contracts.py`

## Follow-up route

Candidate next splits are federation seams, diagnostic-spine contracts,
machine-fit evidence checks, or active-topology language guards.
