# LIFECYCLE

## Canonical lifecycle model

The stack should be operated through explicit profiles and a systemd user entrypoint.

## Intended lifecycle surfaces

### Human-facing wrappers

Planned wrapper family:
- `aoa-up`
- `aoa-down`
- `aoa-status`
- `aoa-logs`
- `aoa-smoke`

### Low-level canonical path

Expected pattern:
- profile resolves to an ordered module list
- compose files are applied in that order
- systemd user unit becomes the stable operator entrypoint

## Bootstrap manual pattern

Until wrappers are reintroduced, the intended manual shape is:

```bash
cd /srv/abyss/Configs
podman compose \
  -f compose/modules/10-storage.yml \
  -f compose/modules/20-orchestration.yml \
  -f compose/modules/30-local-inference.yml \
  up -d
```

Optional modules should be layered explicitly rather than assumed.

## Lifecycle rule

A profile is a declared set of modules.
A module is a declared concern.
Nothing should start just because it once happened to live in a giant file.
