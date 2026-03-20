# REFERENCE PLATFORM

## Reference operating posture

- Fedora 43
- rootless Podman
- systemd user units
- `/srv/abyss-stack` as the canonical runtime root
- `/abyss` as an optional mounted vault for heavy data

## Fedora-first means

The primary operational target is Fedora.
That is where:
- path defaults are anchored
- SELinux-aware volume posture is assumed
- rootless Podman is treated as canonical
- systemd user units are part of the normal lifecycle model

## Windows-usable means

Windows is supported as a source and workflow environment, not as the canonical native runtime target for the current compose surface.

Recommended Windows shape:
- source checkout on Windows host wherever convenient
- runtime deployment inside WSL2 or a Linux-oriented Podman machine
- canonical runtime root inside that Linux layer remains `/srv/abyss-stack`
- optional host vault path may be mapped into the Linux runtime as `/abyss`

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
- a local AI stack rooted under `/srv/abyss-stack`
- an Intel-aware branch of the inference surface
