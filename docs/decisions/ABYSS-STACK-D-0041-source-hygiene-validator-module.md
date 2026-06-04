# Source Hygiene Validator Module

- Decision ID: ABYSS-STACK-D-0041
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/source_hygiene.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, source/runtime boundary, public mirror hygiene
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: cross-mechanic
- Guard families: validation lane, source/runtime boundary, mirror hygiene
- Posture: accepted second validator-module split

## Context

After the script-surface split, the next coherent `validate_stack.py` owner
surface was source hygiene. These checks do not validate compose shape,
mechanic package contracts, or runtime service availability. They protect the
source checkout from accidentally preserving host-local paths, stale active
sibling roots, moved mechanic doc references, and tracked files that are unsafe
for the public GitHub mirror.

Keeping those checks buried in the root validator made the source/runtime
boundary harder to see. It also mixed text-file scanning and tracked-file
classification with unrelated topology checks.

## Options considered

- Keep source hygiene inside `scripts/validate_stack.py`.
- Move source hygiene rules and constants fully into a new manifest-backed
  policy.
- Move source hygiene implementation into a focused module and keep root
  compatibility only as a temporary extraction bridge.

## Decision

Move source hygiene implementation into
`scripts/validators/source_hygiene.py`.

During the extraction bridge, root compatibility functions and rule constants
remained in `scripts/validate_stack.py` while implementation moved into the
focused module. D-0063 closes that bridge: source-hygiene policy, constants,
and focused tests now route directly to `scripts/validators/source_hygiene.py`.

## Rationale

This split matches one pressure: the repository must stay source/install-only
and portable while still describing deployed runtime roots where appropriate.
That boundary is independent from operator command wrappers and independent
from mechanic-local topology.

The bridge-compatible split reduced root-validator implementation weight
without changing caller contracts during extraction. It also gave later changes
a clear destination when they touched mirror hygiene or stale source/runtime
path rules.

## Consequences

- Positive: source/runtime hygiene has an owner module.
- Positive: public mirror policy is separated from mechanics and script
  command validation.
- Positive: existing tests and direct callers stayed stable during the
  extraction bridge.
- Tradeoff: the first slice left constants in the root until the later
  owner-constant migration completed.
- Follow-up: split the next owner surface only when its tests and inventory
  name the module boundary first.

## Source surfaces

- `scripts/validators/source_hygiene.py`
- `scripts/validate_stack.py`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `tests/test_source_topology_validator_modules.py`
- `tests/test_validation_topology.py`
- `tests/test_script_topology.py`

## Follow-up route

Candidate next splits are required source files/root residual topology,
generated diagnostic read models, federation seams, or machine-fit evidence
checks, whichever has the clearest owner surface and focused test coverage.
