# WINDOWS PERFORMANCE

This document explains where Windows plus WSL performance usually bends for `abyss-stack`.

## Core idea

The main risk is not "WSL exists".

The main risk is crossing the Windows filesystem and Linux filesystem boundary too often during Linux-heavy runtime work.

## Hot versus cold data

### Hot data
Keep these in the Linux filesystem when they are active:

- `${AOA_STACK_ROOT}`
- model directories in active use
- logs
- container state
- caches hit constantly by Linux services

### Cold or archival data
These may live on the Windows side if you choose:

- backup archives
- large media collections not hit constantly
- dormant knowledge stores
- export bundles

## What to compare when benchmarking

Use the same preset or profile and compare these conditions:

1. source on Windows, runtime hot data in WSL ext4
2. source on Windows, runtime hot data also forced through Windows-mounted paths

Then compare:

- `doctor`
- `first-run`
- `render-config`
- first service startup
- first model load
- repeated model load
- log and config-heavy tasks

## Performance rule of thumb

Source checkout convenience on Windows is fine.

Hot runtime activity should stay in Linux.

## Current parity limits

### Intel/OpenVINO
The current Intel path still assumes `/dev/dri`, so WSL should be treated as experimental here until the device contract is explicitly tested.

### Monitoring
The current monitoring module carries Linux-host assumptions such as `cadvisor`, `/dev/kmsg`, and host mounts. Treat this as Linux-first until a WSL-specific path is proven.

## Suggested measurement notebook

Record at least:

- Windows version
- WSL version
- distro name
- whether systemd is enabled
- runtime root location
- whether models live in WSL ext4 or a mounted Windows path
- preset/profile used
- overlays used
- rough startup and first-response timings

If a platform-specific quirk or tuning decision shows up, capture one bounded platform-adaptation record instead of leaving the result in chat memory only:

```bash
scripts/aoa-platform-adaptation \
  --mode private \
  --title "Windows or WSL seam title" \
  --summary "One bounded summary" \
  --issue-class performance \
  --write "${AOA_STACK_ROOT}/Logs/platform-adaptations/latest/latest.private.json"
```

That artifact is intentionally small enough to export to another runtime root or to carry from Linux to Windows plus WSL on the same machine.

The goal is not mythology.

The goal is one clear map of where the bridge is smooth and where it still drags.
