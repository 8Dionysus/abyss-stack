# Runtime Hygiene Validator Module

- Decision ID: ABYSS-STACK-D-0051
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/runtime_hygiene.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, runtime lifecycle, status readout
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: runtime-lifecycle, diagnostic-spine
- Guard families: validation lane, status readout, runtime boundary
- Posture: accepted tenth validator-module split

## Context

After the diagnostic-spine validator split, `scripts/validate_stack.py` still
held the runtime hygiene contracts for gateway cache status, usage snapshots,
and the local ops doctor split.

These checks protect optional status readout artifacts. They do not prove live
service availability, add endpoints, or turn `aoa-doctor` into a usage monitor.

## Options considered

- Keep runtime hygiene contracts inside `scripts/validate_stack.py`.
- Fold them into the diagnostic-spine validator because the doctor split is
  referenced there.
- Create a focused `scripts/validators/runtime_hygiene.py` module for
  runtime-lifecycle status readouts and the readiness-only doctor split.

## Decision

Create `scripts/validators/runtime_hygiene.py` and move the implementation of
`validate_runtime_hygiene_contracts` into it.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
mechanic-local tests and callers.

## Rationale

Gateway cache status and usage snapshots belong to runtime lifecycle status
readouts. The doctor split is included only because it bounds those readouts
away from readiness exit semantics. A focused module keeps that boundary easy
to inspect without mixing it into federation, diagnostic surface, or
machine-fit validation.

## Consequences

- Positive: runtime status readout docs, schemas, examples, and doctor split
  posture have a focused owner module.
- Positive: direct module tests now cover schema object shape and billing-term
  drift without going through the root validator.
- Positive: existing callers stayed stable during the extraction bridge;
  D-0063 now routes focused callers to `scripts/validators/runtime_hygiene.py`.
- Tradeoff: the module spans runtime-lifecycle and a diagnostic-spine doctor
  doc because the contract is explicitly about preserving the boundary between
  optional status readouts and readiness-only doctor behavior.

## Source surfaces

- `scripts/validators/runtime_hygiene.py`
- `scripts/validate_stack.py`
- `mechanics/runtime-lifecycle/parts/status-readouts/`
- `mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md`
- `tests/test_runtime_hygiene_validator_module.py`
- `mechanics/runtime-lifecycle/parts/status-readouts/tests/test_runtime_hygiene.py`

## Follow-up route

Candidate next splits are machine-fit evidence posture or return-policy runtime
contracts.
