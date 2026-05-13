# Machine Fit Provenance

This package descends from reference-platform notes, host-facts capture,
machine-fit policy, platform adaptation, Windows bridge, and stack-side
`abyss-machine` bridge work.

The refactor pattern is:

- keep public reference expectations in source
- keep private live host facts outside source history
- keep operator-facing wrappers in `scripts/`
- keep capture, fit, bridge, and adaptation implementations under package
  parts
- keep model-card and tuning docs close to machine-fit while trials remain
  under inference-pilots

## Owner Boundary

`abyss-stack` owns runtime-facing fact schemas, advisory fit records, and
profile/tuning posture. `/srv/abyss-machine`, the host OS, hardware, drivers,
Podman storage, caches, and live provisioning remain outside this source
mirror. Model evaluation truth belongs to evaluation owners, not host-fit docs.

## Current Bridges

- [PARTS.md](PARTS.md) maps host facts, machine bridge, fit records, platform
  adaptation, reference platform, inference tuning, and Windows bridge parts.
- [parts/machine-bridge/docs/MACHINE_BRIDGE.md](parts/machine-bridge/docs/MACHINE_BRIDGE.md)
  owns stack-side read-only machine bridge posture.
- [parts/fit-record/docs/MACHINE_FIT_POLICY.md](parts/fit-record/docs/MACHINE_FIT_POLICY.md)
  owns fit-record policy.
- [parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md](parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md)
  owns adaptation posture.
- [../inference-pilots/README.md](../inference-pilots/README.md) owns local
  model trial and promotion evidence.
