# AGENTS.md

Local guidance for privileged system unit skeletons in `systemd/system/`.
Read the repository root `AGENTS.md` and `systemd/AGENTS.md` first.

## Scope

This directory stores source-managed system-wide unit skeletons that are needed
before rootless user services can work correctly on this host.

## Contract

- Keep this directory small and explicit.
- `managed-units.txt` is the allowlist consumed by
  `scripts/aoa-install-systemd --system-units`.
- Installing these units requires root or `pkexec`; source edits alone must not
  start, stop, restart, enable, disable, or mask system services.
- Units here may call host-owned `abyss-machine` commands, but they do not move
  host-layer implementation authority into `abyss-stack`.
- Do not put secrets, live state, generated logs, or machine-private captures in
  this source directory.

## Privileged install route

Only when an operator explicitly intends to install the allowlisted system
units, use the deployed Configs mirror route:

```bash
pkexec /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-install-systemd --system-units
```

That route backs up existing regular files under `/etc/systemd/system`,
installs root-owned copies of the allowlisted units, and runs
`systemctl daemon-reload`. It does not start, stop, restart, enable, disable,
or mask services.

## Verify

```bash
systemd-analyze verify systemd/system/*.service systemd/system/*.timer
bash -n scripts/aoa-install-systemd
python scripts/validate_stack.py
```
