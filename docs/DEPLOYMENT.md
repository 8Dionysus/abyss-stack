# DEPLOYMENT

This document explains how a source checkout becomes a deployed Fedora-first runtime tree.

## Core distinction

The source checkout and the deployed runtime tree are not the same thing.

Typical shape:
- source checkout anywhere convenient
- deployed runtime at `/srv/abyss-stack`
- optional heavy-data vault at `/abyss`

## Scenario A: Fedora-native source checkout

Example:
- source checkout at `~/src/abyss-stack`
- deployed runtime at `/srv/abyss-stack`

Suggested flow:

```bash
cd ~/src/abyss-stack
scripts/aoa-install-layout
scripts/aoa-sync-configs
```

Then create or place the real secret-bearing files under:

```text
/srv/abyss-stack/Secrets/Configs/
```

## Scenario B: Windows checkout plus Linux runtime

Example:
- source checkout on Windows host at `D:\src\abyss-stack`
- Linux runtime inside WSL2 or a Podman-oriented Linux layer at `/srv/abyss-stack`

Suggested logic:
1. keep editing in the Windows checkout if that is convenient
2. run the deployment bridge scripts inside the Linux layer against the repo view available there
3. deploy into `/srv/abyss-stack`
4. optionally map a Windows host vault path into `/abyss`

The important thing is not where the source lives.
The important thing is that the deployed runtime still becomes `/srv/abyss-stack` inside Linux.

## What the helper scripts do

### `scripts/aoa-install-layout`

Creates the non-destructive runtime directory skeleton under `${AOA_STACK_ROOT}`.
It does not delete existing data.

### `scripts/aoa-sync-configs`

Copies repo-managed stack material from the source checkout into `${AOA_CONFIGS_ROOT}`.
By default it is non-destructive.
An explicit `--delete` mode exists for a tighter mirror when that is desired.

## Recommended first deployment flow

```bash
export AOA_STACK_ROOT=/srv/abyss-stack
export AOA_CONFIGS_ROOT=/srv/abyss-stack/Configs

scripts/aoa-install-layout
scripts/aoa-sync-configs
```

Then inspect:

```bash
aoa-status --profile core
```

Or manually use the deployed scripts:

```bash
/srv/abyss-stack/Configs/scripts/aoa-up --profile core
```

## systemd user install

After the deployed config tree exists:

```bash
mkdir -p ~/.config/systemd/user
ln -sf /srv/abyss-stack/Configs/systemd/user/podman-compose-abyss.service ~/.config/systemd/user/podman-compose-abyss.service
systemctl --user daemon-reload
systemctl --user enable --now podman-compose-abyss.service
```

## Safety note

The helper scripts are meant to be boring and explicit.
They should not guess secrets, delete live service data by surprise, or blur the line between checkout paths and runtime paths.
