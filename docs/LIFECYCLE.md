# LIFECYCLE

## Canonical lifecycle model

The stack should be operated through explicit profiles and a systemd user entrypoint.

## Human-facing wrappers

The repository now includes these wrapper scripts under `scripts/`:
- `aoa-up`
- `aoa-down`
- `aoa-status`
- `aoa-logs`
- `aoa-smoke`
- `aoa-wait`

They resolve a profile into an ordered compose module list.

## Low-level canonical path

Expected pattern:
- profile resolves to an ordered module list
- compose files are applied in that order
- systemd user unit becomes the stable operator entrypoint

## Bootstrap manual pattern

Until wrappers are installed into the live runtime path, the intended manual shape is:

```bash
cd /srv/abyss/Configs
podman compose \
  -f compose/modules/10-storage.yml \
  -f compose/modules/20-orchestration.yml \
  -f compose/modules/30-local-inference.yml \
  up -d
```

Optional modules should be layered explicitly rather than assumed.

## Systemd user surface

A first unit skeleton now lives at:
- `systemd/user/podman-compose-abyss.service`

Its expected deployed location is:
- `~/.config/systemd/user/podman-compose-abyss.service`

It assumes the deployed runtime tree exists under:
- `/srv/abyss/Configs`

## Profile rule

A profile is a declared set of modules.
A module is a declared concern.
Nothing should start just because it once happened to live in a giant file.
