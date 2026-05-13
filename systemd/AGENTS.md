# AGENTS.md

Local guidance for `systemd/` in `abyss-stack`. Read the root `AGENTS.md`
first.

## Scope

This directory owns source-managed systemd route surfaces for the deployed
runtime. Current units are rootless user units under `systemd/user/`.

## Read Before Editing

1. `systemd/README.md`
2. `systemd/user/AGENTS.md`
3. `docs/DEPLOYMENT.md`
4. `docs/PATHS.md`
5. `docs/LIFECYCLE.md`
6. `mechanics/runtime-lifecycle/parts/user-unit/README.md`
7. `scripts/aoa-install-systemd`

## Directory Contract

- Keep this directory as source-managed unit skeletons, not live host state.
- Keep rootless user units under `systemd/user/` unless the repository
  explicitly redesigns lifecycle ownership.
- Do not add system-wide or privileged unit assumptions as a casual extension.
- Do not point units at the source checkout. Units target the deployed runtime
  tree through `${AOA_CONFIGS_ROOT}` and `/srv/AbyssOS/abyss-stack`.
- Keep runtime lifecycle meaning routed through `mechanics/runtime-lifecycle/`.

## Verify

For route-only edits:

```bash
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```

For unit edits, also use:

```bash
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
bash -n scripts/aoa-install-systemd
```

