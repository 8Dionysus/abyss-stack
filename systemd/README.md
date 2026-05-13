# systemd

This directory stores source-managed systemd unit skeletons for the deployed
runtime.

## Current Routes

- [user](user/README.md): rootless `systemd --user` unit skeletons.

## Contract

Units here are source inputs for deployment into the runtime environment. They
are not live host state, and they should keep pointing at deployed
`${AOA_CONFIGS_ROOT}` rather than the source checkout.

Runtime lifecycle ownership is routed through
[runtime-lifecycle user-unit](../mechanics/runtime-lifecycle/parts/user-unit/README.md).
