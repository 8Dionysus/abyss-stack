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

## Assumption

The unit expects the deployed runtime tree to exist under:
- `/srv/abyss/Configs`
