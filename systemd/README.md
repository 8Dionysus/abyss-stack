# systemd

This directory stores source-managed systemd unit skeletons for the deployed
runtime.

## Current Routes

- [user](user/README.md): rootless `systemd --user` unit skeletons, including
  the stack runner and managed host-local user-service adapters.
- [system](system/README.md): small privileged support-unit skeletons for the
  local working stack.

## Contract

Units here are source inputs for deployment into the runtime environment. They
are not live host state, and they should keep pointing at deployed
`${AOA_CONFIGS_ROOT}` rather than the source checkout.

Use `scripts/aoa-install-systemd --all-user-units` after config sync when the
allowlisted user units should be linked from the deployed Configs mirror into
`~/.config/systemd/user`.

Use `pkexec /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-install-systemd --system-units`
only when the allowlisted privileged support units should be linked into
`/etc/systemd/system`. That path installs root-owned unit copies and reloads the
system daemon but does not restart or enable units.

Runtime lifecycle ownership is routed through
[runtime-lifecycle user-unit](../mechanics/runtime-lifecycle/parts/user-unit/README.md).
