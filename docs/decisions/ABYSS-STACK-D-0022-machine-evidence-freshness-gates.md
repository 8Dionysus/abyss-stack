# Machine Evidence Freshness Gates

- Decision ID: ABYSS-STACK-D-0022
- Status: accepted
- Date: 2026-05-14
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-14
- Surface classes: machine evidence, validation guard
- Stack lanes: machine fit
- Mechanic parents: machine-fit
- Guard families: host evidence freshness, validation lane
- Posture: accepted freshness gate rationale

## Context

`abyss-stack` already has a read-only `abyss-machine` bridge under
`mechanics/machine-fit/parts/machine-bridge/`, and lifecycle wrappers already
consume the latest private machine-fit record when composing runtime shape.

That means an old record can still affect operator posture. A file existing
under `Logs/machine-fit/` or `Logs/machine-bridge/` is useful evidence, but it
is not enough to prove that the evidence matches the current host, kernel,
bridge version, or launch window.

## Options considered

1. Keep `aoa-doctor` checking only that machine evidence files exist.
2. Make `abyss-machine` write directly into the stack runtime root whenever its
   facts change.
3. Keep `abyss-machine` read-only and make stack-side doctor/status surfaces
   warn when runtime-local machine evidence is stale or mismatched.

## Decision

Use option 3.

`abyss-stack` keeps ownership of runtime-local evidence under `${AOA_STACK_ROOT}/Logs/`.
`abyss-machine` remains the host owner and read-only evidence provider.
`aoa-doctor` now treats machine-fit and machine-bridge records as current only
when they are parseable, fresh enough for the configured budget, and consistent
with the current host or bridge summary.

## Rationale

This preserves the boundary chosen by the machine-bridge decision while closing
the operational gap where stale evidence looked green. The stack is allowed to
consume machine evidence, but the host layer does not silently mutate stack
runtime logs or source truth.

The warning posture stays soft by default because old evidence can still be
useful for diagnosis. Strict mode can promote warnings to a hard stop when an
operator wants a cutover-grade gate.

## Consequences

- `aoa-doctor` reports stale or mismatched machine evidence instead of treating
  any latest file as sufficient.
- Operators should refresh machine-bridge and private machine-fit evidence
  through the active machine-fit route before live cutover,
  long-running local AI, or launch-window review.
- Source-root detection in autonomy and diagnostic helpers must use the
  current `docs/install/DEPLOYMENT.md` marker, not the old flat docs path.
- The residual risk is intentional: freshness gates warn; they do not replace
  source/deployed parity, runtime health, or benchmark evidence.

## Source surfaces

- `mechanics/diagnostic-spine/parts/doctor-readiness/aoa_doctor.sh`
- `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`
- `mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`
- `mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md`
- `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`

## Follow-up route

If the freshness policy becomes too weak or too strict, adjust the stack-side
doctor thresholds and tests first. Do not make `abyss-machine` a writer into
`abyss-stack` runtime roots.
