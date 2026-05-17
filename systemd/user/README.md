# systemd user units

This directory stores user-unit skeletons for the deployed runtime.

## Current units

- `podman-compose-abyss.service`
- `abyss-stack-resource-guards-apply.service`
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
for the selected preset/profile. It can also persist bounded compose overlays
with `--overlay <compose-file>`, which writes `AOA_EXTRA_COMPOSE_FILES` into the
same drop-in. Preserve the current host preset and layer the `federation`
profile whenever the deployed `langchain-api` federated consumer is enabled.
Pair overlays with an explicit preset or profile so the drop-in always describes
the full intended runtime shape.

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
- `abyss-stack-resource-guards-apply.service`, a manual one-shot unit that runs
  `aoa-apply-resource-guards --wait-game-guard-clear` and applies staged cgroup
  limits only after the game guard clears
- warm dictation and TTS services, plus the `gemma4.spark` stack endpoint
  bridge
- TTS keep-warm timer that periodically exercises the protected warm server
  through `abyss-machine resource launch`
- `gemma4.spark` monitor/digest/micro/jobs timers, nervous, process, storage,
  topology, and doctor timers
- `ydotoold.service` for dictation paste support
- AoA closeout and stats path units that watch owner-local receipt surfaces

The units intentionally consume host-owned commands such as `abyss-machine`
instead of copying host-layer implementation into `abyss-stack`.

For the current Gemma 4 E2B shape, `abyss-stack` owns the live `llama-cpp`
serving endpoint at `http://127.0.0.1:11435`. The host `gemma4.spark`
controller and timers consume that endpoint for evidence, digest, micro, and
jobs artifacts. Keep `abyss-gemma4-spark.service` and
`abyss-gemma4-spark.timer` disabled in stack-owned mode so they do not launch a
second host-local `llama-server`.

System-wide support units have a separate privileged route under
[`../system`](../system/README.md).

## Assumption

The unit expects the deployed runtime tree to exist under:
- `/srv/AbyssOS/abyss-stack/Configs`
