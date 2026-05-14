# systemd user units

This directory stores user-unit skeletons for the deployed runtime.

## Current unit

- `podman-compose-abyss.service`

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

Prefer `scripts/aoa-install-systemd` when you need a durable runtime selection:

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now
```

That command keeps the checked-in unit generic and writes a host-local drop-in
for the selected preset/profile. Preserve the current host preset and layer the
`federation` profile whenever the deployed `langchain-api` federated consumer is
enabled.

## Assumption

The unit expects the deployed runtime tree to exist under:
- `/srv/AbyssOS/abyss-stack/Configs`
