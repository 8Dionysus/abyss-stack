# User Unit

Routes `systemd/user/podman-compose-abyss.service` and
`scripts/aoa-install-systemd`, with the implementation in
`mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`.

User units must point at runtime paths, not the source checkout.

`aoa-install-systemd --preset <name>` and `--profile <name>` write a small
runtime-selection drop-in next to the linked unit. Add `--restart-now` when the
unit is already active and the new selection should take effect immediately.
Repeated flags and comma-separated forms both write the same comma-separated
systemd environment value.
Use that path for durable host-local choices such as
`--preset intel-full --profile federation`; do not bake machine-specific profile
selection into the source unit skeleton.

When `Secrets/Configs/langchain-api.env` enables the federated live consumer,
the selected user-unit shape must include the `federation` profile so
`route-api` survives the next systemd start.
