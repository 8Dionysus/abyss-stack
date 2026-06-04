# Script Surface Validator Module

- Decision ID: ABYSS-STACK-D-0040
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/script_surface.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, source/runtime boundary
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: cross-mechanic
- Guard families: validation lane, source/runtime boundary
- Posture: accepted first validator-module split

## Context

After `docs/validation/` and `docs/testing/` established command authority,
script topology, validator inventory, and test topology, the next pressure was
to start reducing `scripts/validate_stack.py` by owner surface rather than by
arbitrary line count.

The clearest first owner surface is the root script command surface.
`abyss-stack` root scripts are not generic utilities: deployment sync mirrors
them into deployed `Configs/scripts/`, while implementation bodies live under
owning mechanic parts. Their validator checks cover required wrapper names,
backend route parity, executable backend posture, and selected high-risk
runtime wrapper snippets.

## Options considered

- Keep all script-surface validation inside `scripts/validate_stack.py`.
- Move script constants and checks fully into a new module.
- Move execution logic into a focused module and keep root compatibility
  only as a temporary extraction bridge.

## Decision

Move operator script-surface validation logic into
`scripts/validators/script_surface.py`.

During the extraction bridge, root compatibility functions and constants
remained in `scripts/validate_stack.py` while implementation moved into the
focused module. D-0063 closes that bridge: script-surface constants and focused
tests now route directly to `scripts/validators/script_surface.py`.

## Rationale

This is the smallest meaningful split: it moves implementation weight out of
the monolith while preserving the root validator entrypoint, test seams, and
existing route-card expectations.

The first slice avoided changing caller contracts while making the new module
responsible for reusable logic. The later wrapper-tail removal moved caller
contracts to the owner module once the full split was stable.

## Consequences

- Positive: script/operator-wrapper validation now has an owner module.
- Positive: the extraction bridge kept direct callers and tests stable until
  D-0063 moved them to the owner module.
- Positive: future script-surface changes can target the module and inventory
  without expanding the root validator body.
- Tradeoff: the first slice left constants in the root until the later
  owner-constant migration completed.
- Follow-up: split the next owner surface only after its inventory entry and
  focused tests name the destination module.

## Source surfaces

- `scripts/validators/script_surface.py`
- `scripts/validate_stack.py`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/SCRIPT_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `tests/test_source_topology_validator_modules.py`
- `tests/test_validation_topology.py`
- `tests/test_script_topology.py`

## Follow-up route

Candidate next splits are generated/diagnostic read models, federation seams,
or machine-fit evidence checks, whichever has the clearest owner surface and
focused test coverage.
