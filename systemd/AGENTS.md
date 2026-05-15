# AGENTS.md

Local guidance for `systemd/` in `abyss-stack`. Read the root `AGENTS.md`
first.

## Scope

This directory owns source-managed systemd route surfaces for the deployed
runtime. Current live-stack units are rootless user units under `systemd/user/`
and a small privileged support allowlist under `systemd/system/`.

## Read Before Editing

1. `systemd/README.md`
2. `systemd/user/AGENTS.md`
3. `systemd/system/AGENTS.md` when privileged support units are touched
4. `docs/install/DEPLOYMENT.md`
5. `docs/runtime/PATHS.md`
6. `docs/operations/LIFECYCLE.md`
7. `mechanics/runtime-lifecycle/parts/user-unit/README.md`
8. `scripts/aoa-install-systemd`

## Directory Contract

- Keep this directory as source-managed unit skeletons, not live host state.
- Keep rootless user units under `systemd/user/` unless the repository
  explicitly redesigns lifecycle ownership.
- Do not add system-wide or privileged unit assumptions as a casual extension;
  `systemd/system/` exists only for explicit support units needed by this
  machine's working service route.
- Do not point units at the source checkout. Units target the deployed runtime
  tree through `${AOA_CONFIGS_ROOT}` and `/srv/AbyssOS/abyss-stack`.
- Keep runtime lifecycle meaning routed through `mechanics/runtime-lifecycle/`.
- Treat `systemd/user/managed-units.txt` as the allowlist for host-local user
  units that may be linked from the deployed Configs mirror. It may reference
  host-owned commands such as `abyss-machine`, but it must not move their source
  ownership into `abyss-stack`.
- Treat `systemd/system/managed-units.txt` the same way for privileged support
  units. Installing it requires root or `pkexec` and must not imply service
  restarts.

## Verify

For route-only edits:

```bash
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```

For unit edits, also use:

```bash
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
systemd-analyze --user verify systemd/user/*.service systemd/user/*.timer systemd/user/*.path
systemd-analyze verify systemd/system/*.service systemd/system/*.timer
bash -n scripts/aoa-install-systemd
```
