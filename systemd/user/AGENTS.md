# AGENTS Rules for coding agents and maintainers working in `systemd/user/`.

## Scope
This directory stores rootless `systemd --user` unit skeletons for the deployed runtime.

## Read before editing
1. `systemd/user/README.md`
2. `docs/DEPLOYMENT.md`
3. `docs/PATHS.md`
4. `docs/LIFECYCLE.md`
5. `scripts/aoa-install-systemd`

## Directory contract
- Units here are user units, not system-wide units.
- They target the deployed runtime tree under `${AOA_CONFIGS_ROOT}` and the canonical runtime root `/srv/AbyssOS/abyss-stack`, not the source checkout.
- The current contract file is `systemd/user/podman-compose-abyss.service`.
- Lifecycle stays rooted in deployed `Configs/scripts/aoa-up` and `Configs/scripts/aoa-down`.

## Unit rules
- Preserve the rootless Fedora-first posture. Do not convert these into privileged or system-wide service assumptions casually.
- Keep explicit environment variables for stack root, configs root, profile, and project name.
- The default profile should stay conservative, currently `core`, unless the repo-level operating contract changes.
- Do not embed secrets or machine-specific source paths in units.
- Do not change lifecycle semantics such as `Type=oneshot`, `RemainAfterExit=yes`, or the start, stop, and reload scripts without checking the runtime wrappers and docs.

## When changing units
- If the unit name, install path, or install behavior changes, update `scripts/aoa-install-systemd` and `systemd/user/README.md`.
- If lifecycle semantics change, update `docs/LIFECYCLE.md` and `docs/DEPLOYMENT.md`.
- Keep the deployed-path assumption explicit. The unit should continue to run from the deployed runtime tree, not from a working checkout.

## Verify
When the host supports systemd user tooling:
```bash
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
scripts/aoa-install-systemd
```

If you are explicitly testing enablement, use:
```bash
scripts/aoa-install-systemd --enable-now
```

## Hard no
- do not point units at the source checkout
- do not assume `/etc/systemd/system` deployment
- do not widen runtime exposure or add privileged service assumptions without explicit redesign
- do not rename the unit without updating the installer and docs
