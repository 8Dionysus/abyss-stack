# Managed Systemd Unit Sources

Status: accepted
Date: 2026-05-14

## Context

`abyss-stack` needs to be the source checkout that can project the working
runtime substrate into the deployed AbyssOS tree. The live machine already uses
several user and system systemd units around the stack runner, `abyss-machine`
readouts, AI resident candidates, nervous-system maintenance, dictation, stats,
and closeout watchers.

Leaving those unit sources only as host-local leftovers makes the source/runtime
route hard to reproduce. Pulling their implementation logic into `abyss-stack`
would be worse: most of the commands they call belong to `abyss-machine` or
sibling owner repositories.

## Options considered

1. Keep only `podman-compose-abyss.service` in the source checkout and leave all
   other units as untracked host state.
2. Move host-service implementation into `abyss-stack` so every unit becomes
   fully stack-owned.
3. Keep source-managed unit skeletons and allowlists in `systemd/`, while
   leaving host-service implementation and live enablement state with their
   owning layers.

## Decision

`systemd/user/` owns rootless user-unit skeletons and a
`managed-units.txt` allowlist for units that may be linked from the deployed
Configs mirror into `~/.config/systemd/user`.

`systemd/system/` owns a small privileged support-unit skeleton set and its own
`managed-units.txt` allowlist for units that may be installed into
`/etc/systemd/system` by an explicit root or `pkexec` route.

`scripts/aoa-install-systemd` may link or install the allowlisted units and
reload the relevant daemon. It must not start, stop, restart, enable, disable,
or mask services in the allowlist modes. Runtime selection drop-ins remain
host-local.

## Rationale

This makes the deployed runtime route reproducible from the source checkout
without pretending that `abyss-stack` owns the host commands behind every unit.
It also keeps the GitHub mirror source-only: the repository carries unit
skeletons, install rules, and public-safe paths, not live service state,
private captures, logs, models, or secrets.

The allowlists keep the bridge light and reviewable. Future agents can see which
units are source-managed, while operators still decide when to install, enable,
or restart them on a real machine.

## Consequences

- Config sync now projects `systemd/` as a source-managed runtime surface.
- `aoa-install-systemd --all-user-units` links allowlisted user units without
  mutating live service state.
- `aoa-install-systemd --system-units` requires root, installs root-owned copies
  of allowlisted privileged units, and reloads the system daemon without
  enabling or restarting them.
- Unit files may consume host-owned commands such as `abyss-machine`, but those
  commands remain outside this repository's implementation authority.
- Per-machine overrides, runtime-selection drop-ins, enablement state, and live
  service status remain host-local.

## Source surfaces

- `systemd/AGENTS.md`
- `systemd/README.md`
- `systemd/user/AGENTS.md`
- `systemd/user/README.md`
- `systemd/user/managed-units.txt`
- `systemd/system/AGENTS.md`
- `systemd/system/README.md`
- `systemd/system/managed-units.txt`
- `mechanics/runtime-lifecycle/parts/user-unit/README.md`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `mechanics/runtime-lifecycle/parts/layout-install/aoa_install_layout.sh`
- `mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh`
- `docs/install/DEPLOYMENT.md`
- `docs/operations/LIFECYCLE.md`
- `scripts/README.md`
- `scripts/validate_stack.py`
- `scripts/validate_nested_agents.py`

## Follow-up route

Revisit through `systemd/`, `mechanics/runtime-lifecycle/parts/user-unit/`, and
`mechanics/machine-fit/` if a unit becomes a first-class stack service, if
machine-owned commands move, or if live enablement should become an explicit
operator workflow rather than a source-only projection.
