# LIFECYCLE

## Canonical lifecycle model

The stack should be operated through explicit profiles and a systemd user entrypoint.

## Deployment preparation

The repository now includes deployment bridge scripts under `scripts/`:
- `aoa-install-layout`
- `aoa-sync-configs`
- `aoa-bootstrap-configs`
- `aoa-check-layout`
- `aoa-install-systemd`

They help bridge from a source checkout into the deployed runtime tree under `${AOA_STACK_ROOT}`.

## Human-facing wrappers

The repository also includes these runtime wrappers under `scripts/`:
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
cd /srv/abyss-stack/Configs
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
- `/srv/abyss-stack/Configs`

## Path note

The wrapper scripts treat the deployed Linux runtime path as distinct from any source checkout path.
This is what makes the repository Fedora-first while still usable from Windows-oriented editing workflows.

## Profile rule

A profile is a declared set of modules.
A module is a declared concern.
Nothing should start just because it once happened to live in a giant file.
