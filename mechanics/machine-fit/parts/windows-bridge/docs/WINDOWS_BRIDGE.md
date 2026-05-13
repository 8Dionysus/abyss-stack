# WINDOWS BRIDGE

This document defines the Windows role inside `abyss-stack`.

## Core rule

There is still only one runtime truth:

- Linux remains the canonical runtime body
- Windows is a host, editing, and launch surface
- WSL is the bridge, not a second substrate

## Why the bridge lives inside `abyss-stack`

Because the repository already owns:

- runtime layout
- deployment bridge scripts
- lifecycle operations
- compose selection logic
- host and runtime path contracts

So the Windows bridge belongs here as a platform slice, not as a second repository that duplicates runtime truth.

## What Windows owns

Windows-host tooling may own:

- PowerShell launchers
- WSL discovery and readiness checks
- Windows-to-WSL path translation
- operator ergonomics
- benchmark helpers
- host-side docs for setup and performance

Windows-host tooling must not become a second compose authority.

## What Linux still owns

Linux still owns:

- the canonical runtime root at `/srv/AbyssOS/abyss-stack`
- rootless Podman lifecycle
- systemd user-unit posture
- the actual composed runtime
- the deployed config tree under `${AOA_CONFIGS_ROOT}`

## Bridge command surface

The bridge entrypoint is:

```powershell
pwsh -File scripts/aoa.ps1 <command> [args...]
```

Examples:

```powershell
pwsh -File scripts/aoa.ps1 host-doctor
pwsh -File scripts/aoa.ps1 doctor --preset agent-full
pwsh -File scripts/aoa.ps1 first-run --strict
pwsh -File scripts/aoa.ps1 up --preset agent-full
pwsh -File scripts/aoa.ps1 status --preset agent-full
pwsh -File scripts/aoa.ps1 down --preset agent-full
```

## Overlay contract

Platform-specific or tuning-specific compose files may be layered with:

- `AOA_EXTRA_COMPOSE_FILES`
- or the PowerShell `-Overlay` parameter

Relative overlay paths are resolved inside `${AOA_CONFIGS_ROOT}`.

Example:

```powershell
pwsh -File scripts/aoa.ps1 up -Overlay compose/tuning/llamacpp.cpu.yml --preset agent-full
```

That keeps profiles and presets canonical while still allowing carefully bounded overlays.

## Current limits

The bridge is intentionally modest in this first landing.

### Intel path

The current Intel/OpenVINO module is still shaped around `/dev/dri`, so WSL parity is not claimed yet.

### Monitoring path

The current monitoring module includes Linux-host assumptions such as `cadvisor` and host mounts, so WSL parity is not claimed yet.

## Operator rule

Use Windows as the control deck.

Use Linux as the engine room.
