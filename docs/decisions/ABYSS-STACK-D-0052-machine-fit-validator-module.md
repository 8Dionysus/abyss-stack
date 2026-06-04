# Machine Fit Validator Module

- Decision ID: ABYSS-STACK-D-0052
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/machine_fit.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, machine evidence, source/runtime boundary
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: machine-fit
- Guard families: validation lane, host evidence posture, machine bridge
- Posture: accepted eleventh validator-module split

## Context

After the runtime hygiene split, `scripts/validate_stack.py` still held
machine-fit checks for reference platform docs, host facts examples, machine
bridge read-only posture, machine-fit profile recommendations, freshness gates,
and platform adaptation examples.

These checks protect public-safe stack-side evidence contracts. They do not
grant `abyss-stack` ownership over the host, `/srv/abyss-machine`, private
captures, storage migration, or accelerator state.

## Options considered

- Keep machine-fit evidence checks inside `scripts/validate_stack.py`.
- Split only the machine bridge checks because it already has package-local
  tests.
- Create a focused `scripts/validators/machine_fit.py` module for the full
  machine-fit evidence posture.

## Decision

Create `scripts/validators/machine_fit.py` and move the implementations of:

- `validate_reference_platform`
- `validate_machine_bridge`
- `validate_machine_integration_freshness_gates`
- `validate_platform_adaptations`

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Reference-platform docs, host facts, machine bridge records, fit records, and
platform adaptations share one owner surface: the stack's public-safe machine
evidence posture. They should be inspected together because the boundary is not
only file layout; it is the claim that stack-side records are advisory and
read-only toward the actual machine.

## Consequences

- Positive: machine-fit evidence posture now has a focused owner module.
- Positive: direct module tests cover bridge mutability, platform-adaptation
  exporter identity, and composition-first machine-fit profiles.
- Positive: root validator API compatibility remains intact.
- Tradeoff: the module also checks diagnostic and governed-execution files
  where they consume machine evidence freshness gates.

## Source surfaces

- `scripts/validators/machine_fit.py`
- `scripts/validate_stack.py`
- `mechanics/machine-fit/`
- `mechanics/diagnostic-spine/parts/doctor-readiness/`
- `mechanics/governed-execution/parts/autonomy-status/`
- `tests/test_machine_fit_validator_module.py`

## Follow-up route

Candidate next splits are return-policy runtime contracts or branch/release
governance contracts.
