# AGENTS Rules for coding agents and maintainers working in `systemd/user/`.

## Scope
This directory stores rootless `systemd --user` unit skeletons for the deployed runtime.

## Read before editing
1. `systemd/user/README.md`
2. `docs/install/DEPLOYMENT.md`
3. `docs/runtime/PATHS.md`
4. `docs/operations/LIFECYCLE.md`
5. `scripts/aoa-install-systemd`

## Directory contract
- Units here are user units, not system-wide units.
- They target the deployed runtime tree under `${AOA_CONFIGS_ROOT}` and the canonical runtime root `/srv/AbyssOS/abyss-stack`, not the source checkout.
- The stack runner contract file is `systemd/user/podman-compose-abyss.service`.
- The live user-service allowlist is `systemd/user/managed-units.txt`.
- Lifecycle stays rooted in deployed `Configs/scripts/aoa-up` and `Configs/scripts/aoa-down`.
- Host-service adapters may call host-owned commands such as `abyss-machine`.
  Keep those commands as consumed dependencies; do not copy host-layer logic or
  private state into this repository.
- Sibling-service adapters own scheduling and the deployed invocation route,
  not the sibling's internal input selection. Prefer the sibling command's
  public defaults over pinning its private registry, inventory, or config paths
  in a unit skeleton.

## Unit rules
- Preserve the rootless Fedora-first posture. Do not convert these into privileged or system-wide service assumptions casually.
- Keep explicit environment variables for stack root, configs root, profile, and project name.
- The default profile should stay conservative, currently `substrate`, unless the repo-level operating contract changes.
- Do not embed secrets or machine-specific source paths in units.
- Do not change lifecycle semantics such as `Type=oneshot`, `RemainAfterExit=yes`, or the start, stop, and reload scripts without checking the runtime wrappers and docs.

## When changing units
- If the unit name, install path, or install behavior changes, update `scripts/aoa-install-systemd`, `systemd/user/managed-units.txt`, and `systemd/user/README.md`.
- If lifecycle semantics change, update `docs/operations/LIFECYCLE.md` and `docs/install/DEPLOYMENT.md`.
- Keep the deployed-path assumption explicit. The unit should continue to run from the deployed runtime tree, not from a working checkout.
- When a unit watches sibling-owned inputs or passes sibling CLI options,
  reconcile it with the current sibling contract and add a deterministic source
  test for the exact adapter boundary.

## Install routes

For a direct manual user-unit reload and enablement test:

```bash
systemctl --user daemon-reload
systemctl --user enable --now podman-compose-abyss.service
```

Prefer the installer when a durable runtime selection should be recorded:

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now
```

To link every user unit named in `managed-units.txt` without starting or
enabling services:

```bash
scripts/aoa-install-systemd --all-user-units
```

## Verify
When the host supports systemd user tooling:
```bash
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
systemd-analyze --user verify systemd/user/*.service systemd/user/*.timer systemd/user/*.path
scripts/aoa-install-systemd
```

If you are explicitly testing enablement, use:
```bash
scripts/aoa-install-systemd --enable-now
```

## Hard no
- do not point units at the source checkout
- do not assume `/etc/systemd/system` deployment
- do not start, stop, restart, disable, or reconfigure host services from a
  source-only unit edit
- do not widen runtime exposure or add privileged service assumptions without explicit redesign
- do not rename the unit without updating the installer and docs
