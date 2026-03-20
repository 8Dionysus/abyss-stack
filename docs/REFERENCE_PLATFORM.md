# REFERENCE PLATFORM

## Reference operating posture

- Fedora 43
- rootless Podman
- systemd user units
- `/srv/abyss` as the canonical runtime root
- `/abyss` as an optional mounted vault for heavy data

## Why this matters

The stack is not just a pile of services.
It is shaped around:
- local-first operation
- recoverable lifecycle control
- explicit storage layout
- minimal host exposure

## Runtime assumptions

- `podman` is the default container runtime
- compose-compatible workflows are expected
- systemd user services are the canonical lifecycle surface
- external heavy data should be treated as optional mounts, not invisible assumptions

## Minimum practical expectations

- modern multi-core CPU
- 32 GB RAM preferred
- fast SSD or NVMe for active state
- enough free headroom for models, service state, and logs

## Known user-specific fit

This repository is intentionally aligned with:
- rootless Podman rather than Docker
- a local AI stack rooted under `/srv/abyss`
- an Intel-aware branch of the inference surface
