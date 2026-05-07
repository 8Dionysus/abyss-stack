# Machine Fit Mechanic

## Mechanic card

Machine fit is the mechanic for reading host capability and tuning posture so
the runtime can choose safer profiles without pretending to own the machine.

### Trigger

Use this package when changing reference-platform docs, host-facts capture,
machine-fit records, platform adaptation, accelerator selection, or future
`abyss-machine` integration.

### abyss-stack owns

- public-safe reference-platform contracts
- runtime-facing host-facts and machine-fit record shape
- platform adaptation policy for stack profile choices
- read-only consumption expectations for machine facts

### Stronger owner split

`abyss-machine` owns machine control-plane facts, caches, storage, and runtime
provisioning. The OS and hardware own live capability. `abyss-stack` consumes
facts and adapts runtime shape.

### Inputs

Public reference specs, private host facts, machine-fit latest records, operator
profile intent, and optional machine bridge data.

### Outputs

Recommended runtime profiles, tuning warnings, fit records, and docs that
explain which facts are advisory versus required.

### Must not claim

- machine ownership
- live accelerator availability without a check
- private facts are public-safe
- a tuning recommendation is a service-health proof

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [runtime-lifecycle](../runtime-lifecycle/README.md) to apply selected
profiles and [inference-pilots](../inference-pilots/README.md) for model trials.

## Active route

Current source surfaces stay in `docs/reference-platform/`, `docs/machine-fit/`,
`docs/platform-adaptations/`, and matching scripts.

