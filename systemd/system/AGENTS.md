# AGENTS.md

Local guidance for privileged system unit skeletons in `systemd/system/`.
Read the repository root `AGENTS.md` and `systemd/AGENTS.md` first.

## Scope

This directory stores source-managed system-wide unit skeletons that are needed
before rootless user services can work correctly on this host.

## Contract

- Keep this directory small and explicit.
- `managed-units.txt` is the allowlist consumed by
  the system-unit installation route in `scripts/aoa-install-systemd`.
- Installing these units requires root or `pkexec`; source edits alone must not
  start, stop, restart, enable, disable, or mask system services.
- Units here may call host-owned `abyss-machine` commands, but they do not move
  host-layer implementation authority into `abyss-stack`.
- Do not put secrets, live state, generated logs, or machine-private captures in
  this source directory.

## Privileged install route

Only when an operator explicitly intends to install the allowlisted system
units, use the deployed Configs mirror route:

Validation is on-demand: use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

That route backs up existing regular files under `/etc/systemd/system`,
installs root-owned copies of the allowlisted units, and runs
the systemd daemon-reload operation. It does not start, stop, restart, enable, disable,
or mask services.

## Verify
