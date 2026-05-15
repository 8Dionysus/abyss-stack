# systemd user units

This directory stores user-unit skeletons for the deployed runtime.

## Current units

- `podman-compose-abyss.service`
- `managed-units.txt` allowlists the host-local user units that can be linked
  from the deployed Configs mirror.

## Expected deployed path

Copy or symlink the unit into:

```text
~/.config/systemd/user/
```

Then reload and enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now podman-compose-abyss.service
```

The checked-in unit defaults to the conservative `substrate` profile. Host-local
drop-ins should carry richer runtime selection rather than editing the source
skeleton for one machine.

Prefer `scripts/aoa-install-systemd` when you need a durable runtime selection:

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now
```

That command keeps the checked-in unit generic and writes a host-local drop-in
for the selected preset/profile. Preserve the current host preset and layer the
`federation` profile whenever the deployed `langchain-api` federated consumer is
enabled.

## Managed live user units

The same installer can also link every unit named in `managed-units.txt`:

```bash
scripts/aoa-install-systemd --all-user-units
```

That mode only links unit files and reloads the user daemon. It does not start,
stop, restart, enable, disable, or mask services. Existing user-unit drop-ins
remain host-local and continue to apply, which lets the stack take ownership of
the unit source path without losing per-machine memory or runtime-selection
overrides.

The current allowlist covers the local working surface:

- `podman-compose-abyss.service`
- warm dictation, TTS, and `gemma4.spark` resident services
- `gemma4.spark`, nervous, process, storage, topology, and doctor timers
- `ydotoold.service` for dictation paste support
- AoA closeout and stats path units that watch owner-local receipt surfaces

The units intentionally consume host-owned commands such as `abyss-machine`
instead of copying host-layer implementation into `abyss-stack`.

System-wide support units have a separate privileged route under
[`../system`](../system/README.md).

## Assumption

The unit expects the deployed runtime tree to exist under:
- `/srv/AbyssOS/abyss-stack/Configs`
