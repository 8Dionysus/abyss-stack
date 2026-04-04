# compose tuning

This directory stores optional compose overlays.

## Rule

Tuning files do not replace modules, profiles, or presets.

They are layered on top of the canonical compose surface through:

- `AOA_EXTRA_COMPOSE_FILES`
- the Windows bridge `-Overlay` parameter

## Resolution rule

Relative overlay paths are resolved inside `${AOA_CONFIGS_ROOT}`.

That means:

- `compose/tuning/llamacpp.cpu.yml`

resolves to:

- `${AOA_CONFIGS_ROOT}/compose/tuning/llamacpp.cpu.yml`

## Placeholder example

- `llamacpp.cpu.yml`

Example on Linux:

```bash
export AOA_EXTRA_COMPOSE_FILES=compose/tuning/llamacpp.cpu.yml
scripts/aoa-up --profile core
```

Example on Windows:

```powershell
pwsh -File scripts/aoa.ps1 up -Overlay compose/tuning/llamacpp.cpu.yml --profile core
```

`llamacpp.cpu.yml` is intentionally a placeholder overlay that proves the overlay path works without claiming a measured or production-grade CPU tuning contract.

## Why this directory exists

Because bounded overlays are healthier than duplicating the stack into platform forks.
