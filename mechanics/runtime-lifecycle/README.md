# Runtime Lifecycle Mechanic

## Mechanic card

Runtime lifecycle is the mechanic for turning source-authored stack shape into
operator-visible runtime behavior without confusing source, deployed mirror, and
live service state.

### Trigger

Use this package when changing install layout, deployment flow, up/down/wait
wrappers, systemd user units, runbook steps, profiles, presets, or service
catalog posture.

### abyss-stack owns

- rootless Podman lifecycle shape
- deployed runtime root and `Configs` mirror expectations
- lifecycle wrapper contracts
- systemd user unit skeletons
- public-safe operator runbook posture

### Stronger owner split

The host OS, Podman, systemd, and `abyss-machine` own their own live facts. AoA
and ToS owner repositories own authored meaning consumed by runtime services.

### Inputs

Source docs, compose profiles and presets, public-safe config, operator intent,
host facts, and deployment sync status.

### Outputs

Dry-run commands, validated lifecycle routes, service start/stop wrappers, and
operator-facing runbook guidance. Package-local status readout contracts may
also describe source-safe runtime log artifacts without claiming they are live.

### Must not claim

- source-only edits are live
- a service is healthy without a live check
- a unit should be enabled or started without explicit operator intent
- runtime lifecycle owns machine provisioning

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [config-projection](../config-projection/README.md) for config material,
[machine-fit](../machine-fit/README.md) for host fit, and
[diagnostic-spine](../diagnostic-spine/README.md) for readiness or truth-goal
checks.

## Active route

Stable operator entrypoints stay in `scripts/`. Runtime-lifecycle
implementation bodies for first-run, layout, start/stop, warmup, wait/smoke,
logs/status, and user-unit helpers live under their owning
`mechanics/runtime-lifecycle/parts/` routes. Runtime cache/usage readout schemas
and examples live in `mechanics/runtime-lifecycle/parts/status-readouts/`, with
regression coverage in `mechanics/runtime-lifecycle/parts/status-readouts/tests/`.
