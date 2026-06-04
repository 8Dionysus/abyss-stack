# Service Selection Validator Module

- Decision ID: ABYSS-STACK-D-0043
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/service_selection.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, runtime topology, service selection
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: runtime-lifecycle
- Guard families: validation lane, runtime topology, source/runtime boundary
- Posture: accepted fourth validator-module split

## Context

`scripts/validate_stack.py` carried the checks for
`docs/runtime/service-selection-policy.v1.json` and
`docs/runtime/service-inventory-2026-05-14.v1.json`. Those checks protect the
source-level description of the currently selected runtime shape: selected
services, opt-in services, required resource guards, profile/module parity, and
the manual screenshot inventory that anchors the policy to observed runtime
evidence.

That owner surface is not generic source topology and it is not a mechanic
package validator. It belongs to the runtime service-selection route and should
be readable as its own validation module.

## Options considered

- Keep service-selection validation inside `scripts/validate_stack.py`.
- Move service policy constants and policy JSON ownership fully into a new
  manifest layer.
- Move implementation into a focused module and keep root compatibility only
  as a temporary extraction bridge.

## Decision

Move service-selection policy and screenshot inventory validation into
`scripts/validators/service_selection.py`.

During the extraction bridge, root compatibility functions passed current
stack constants, compose profile readers, and policy paths into the focused
module. D-0063 closes that bridge: service-selection constants and focused
tests now route directly to `scripts/validators/service_selection.py`.

Add focused unit tests in `tests/test_service_selection_validator_module.py` so
the module boundary is tested without requiring a full repository runtime
shape.

## Rationale

The service-selection checks are policy-rich and specific. Extracting them
removes a meaningful runtime topology guard from the monolith while preserving
behavior and release-gate compatibility.

Parameterizing the module kept the root validator as the command entrypoint
while making the validator independently testable with small source fixtures.

## Consequences

- Positive: runtime service-selection validation has an owner module.
- Positive: selected-service guard and screenshot-inventory parity now have
  focused tests.
- Positive: existing callers stayed stable during the extraction bridge.
- Tradeoff: the first slice left service-selection constants in the root until
  the later owner-constant migration completed.
- Follow-up: future service policy changes should update the focused module
  and tests before widening root validation.

## Source surfaces

- `scripts/validators/service_selection.py`
- `scripts/validate_stack.py`
- `docs/runtime/SERVICE_SELECTION.md`
- `docs/runtime/service-selection-policy.v1.json`
- `docs/runtime/service-inventory-2026-05-14.v1.json`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `docs/testing/test_inventory.json`
- `tests/test_service_selection_validator_module.py`
- `tests/test_validation_topology.py`
- `tests/test_script_topology.py`

## Follow-up route

Candidate next splits are federation seams, diagnostic-spine contracts,
machine-fit evidence checks, or questbook validation, whichever can move with a
focused test seam and owner-module routing.
