# Source Structure Validator Module

- Decision ID: ABYSS-STACK-D-0042
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/source_structure.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, source topology
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: cross-mechanic
- Guard families: validation lane, source topology
- Posture: accepted third validator-module split

## Context

`scripts/validate_stack.py` still carried two small but important source
structure guards: required source-file presence and residual root/doc topology.
These checks protect the checkout shape before deeper mechanic and runtime
contracts run.

The checks are not script command validation, source/runtime hygiene, compose
validation, or mechanic-package validation. They answer a simpler question:
does the source checkout still expose the mandatory route surfaces, managed
unit skeletons, and district moves established by the docs refactor?

## Options considered

- Keep required-file and residual-root checks inside `scripts/validate_stack.py`.
- Move the checks directly into docs inventory tests only.
- Move implementation into a focused module while keeping temporary root
  compatibility during the extraction bridge.
- Promote the required-file manifest into the focused source-structure module.

## Decision

Move required source-file and residual root topology implementation into
`scripts/validators/source_structure.py`.

The required-file manifest also belongs to the source-structure module. The
root validator passes `source_structure.required_files(ROOT)` into the module
and does not keep a parallel root manifest authority.

The public root wrapper functions were kept only during the extraction bridge.
D-0063 closes that bridge and routes focused tests directly to the owner
module.

## Rationale

This split is intentionally small. It removes a source-topology guard from the
monolith without changing behavior or widening policy. The resulting module
gives future required-file and docs-district changes a clear owner surface.

It also keeps the distinction between structure and hygiene visible:
`source_structure.py` protects required checkout shape, while
`source_hygiene.py` protects portability and public mirror safety.

## Consequences

- Positive: required source-file and root residual topology checks now have an
  owner module.
- Positive: the required-file manifest now has the same owner as the check.
- Positive: source structure and source hygiene are separate validation
  concerns.
- Tradeoff: ad hoc callers that imported root wrapper functions must move to
  `scripts/validators/source_structure.py` or use the root CLI.
- Follow-up: split larger owner surfaces only when the test and inventory route
  can name the module boundary clearly.

## Source surfaces

- `scripts/validators/source_structure.py`
- `scripts/validate_stack.py`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `tests/test_source_topology_validator_modules.py`
- `tests/test_validation_topology.py`
- `tests/test_script_topology.py`

## Follow-up route

Candidate next splits are generated diagnostic read models, federation seams,
machine-fit evidence checks, or mechanic package topology, whichever can move
with explicit owner-module routing.
