# Diagnostic Spine Mechanic

## Mechanic card

Diagnostic spine is the mechanic for read-only runtime self-location: collect
readiness, truth-goal status, drift evidence, anchors, companion summaries, and
repair handoff candidates without performing repair.

### Trigger

Use this package when changing `aoa-doctor`, `aoa-diagnose`, diagnostic schemas,
diagnostic examples, generated diagnostic catalog, reviewed diagnosis refs, or
truth-goal status docs.

### abyss-stack owns

- readiness-only doctor posture
- diagnostic read model
- diagnostic schemas and public-safe examples
- generated diagnostic surface catalog
- repair handoff candidate emission

### Stronger owner split

Repair workflows belong to `aoa-skills` and owner repositories. Runtime can
write evidence and handoff candidates, but it does not decide final repair,
proof, memory, or owner acceptance.

### Inputs

Doctor output, autonomy status, machine-fit records, last-good anchors,
reviewed diagnosis refs, and explicit truth goals.

### Outputs

Diagnostic target, session, companion, anchor ref, reviewed ref, and repair
handoff JSON surfaces.

### Must not claim

- readiness means live availability
- diagnostics repaired the system
- a handoff candidate is owner acceptance
- private machine facts are public-safe

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [runtime-repair](../runtime-repair/README.md) when the diagnostic output
becomes repair-safe closeout work, and [machine-fit](../machine-fit/README.md)
when the gap is host-specific.

## Active route

Current source surfaces stay in `mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md`, `mechanics/diagnostic-spine/docs/DOCTOR.md`,
`scripts/aoa-diagnose`, `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/`, `mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/`,
and `mechanics/diagnostic-spine/parts/diagnose-wrapper/tests/test_aoa_diagnose.py`.
