# DEPLOYMENT

This document explains how a source checkout becomes a deployed Fedora-first runtime tree.

## Core distinction

The source checkout and the deployed runtime tree are not the same thing.

Typical shape:
- source checkout anywhere convenient
- deployed runtime at `/srv/abyss-stack`
- optional heavy-data vault at `/abyss`

## Fastest guided route

If you want the least-friction path, use:

```bash
scripts/aoa-doctor
scripts/aoa-first-run --strict
```

`aoa-first-run --strict` is strict about layout and bootstrapped config presence, but still ignores missing secrets on that first pass by design.

Then create secrets per [SECRETS_BOOTSTRAP](SECRETS_BOOTSTRAP.md).

## Scenario A: Fedora-native source checkout

Example:
- source checkout at `~/src/abyss-stack`
- deployed runtime at `/srv/abyss-stack`

Suggested flow:

```bash
cd ~/src/abyss-stack
scripts/aoa-doctor
scripts/aoa-install-layout
scripts/aoa-sync-configs
scripts/aoa-bootstrap-configs
scripts/aoa-check-layout --ignore-secrets --strict
scripts/aoa-profile-modules --profile core
scripts/aoa-profile-endpoints --profile core
```

Then bootstrap real secret-bearing files as described in [SECRETS_BOOTSTRAP](SECRETS_BOOTSTRAP.md).

## Scenario B: Windows checkout plus Linux runtime

Example:
- source checkout on Windows host at `D:\src\abyss-stack`
- Linux runtime inside WSL2 or a Podman-oriented Linux layer at `/srv/abyss-stack`

Suggested logic:
1. keep editing in the Windows checkout if that is convenient
2. run the deployment bridge scripts inside the Linux layer against the repo view available there
3. deploy into `/srv/abyss-stack`
4. bootstrap public-safe runtime config files from templates
5. bootstrap secrets separately
6. optionally map a Windows host vault path into `/abyss`

The important thing is not where the source lives.
The important thing is that the deployed runtime still becomes `/srv/abyss-stack` inside Linux.

## What the helper scripts do

### `scripts/aoa-doctor`

Checks host-side and runtime-side readiness for the Fedora-first model.
It reports missing commands, platform mismatches, vault mount state, and Intel-specific hints such as `/dev/dri` presence.
Use `--strict` if warnings should fail the command.

### `scripts/aoa-install-layout`

Creates the non-destructive runtime directory skeleton under `${AOA_STACK_ROOT}`.
It does not delete existing data.

### `scripts/aoa-sync-configs`

Copies repo-managed stack material from the source checkout into `${AOA_CONFIGS_ROOT}`.
By default it is non-destructive.
An explicit `--delete` mode exists for a tighter mirror when that is desired.

### `scripts/aoa-bootstrap-configs`

Copies public-safe config templates into the runtime tree if the destination files are missing.
Use `--force` only when you explicitly want template content to overwrite existing runtime config files.

### `scripts/aoa-check-layout`

Checks the runtime tree and reports missing directories, missing template-derived config files, and missing secret-bearing files.
Use `--ignore-secrets` for the first bootstrap pass before secrets exist.
Use `--strict` if warnings should fail the command.

### `scripts/aoa-install-systemd`

Links the user-unit skeleton into `~/.config/systemd/user/` and reloads the user daemon.
Use `--enable-now` if you want it enabled and started immediately.

### `scripts/aoa-preset-profiles`

Shows which profiles a preset resolves to.
Use `--paths` if you want preset and profile file paths.

### `scripts/aoa-profile-modules`

Shows which compose modules a profile resolves to.
Use `--paths` if you want the absolute module file paths.
You can pass several profiles or presets.

### `scripts/aoa-profile-endpoints`

Shows the host-facing endpoints and internal-only notes for a profile.
Use it before or after startup to understand what should become reachable.
You can pass several profiles or presets.

### `scripts/aoa-render-services`

Shows the final service list from the actual composed runtime view.
This is deeper runtime truth than module or endpoint narration because it comes from Compose itself after profile composition.
You can pass several profiles or presets.

### `scripts/aoa-render-config`

Renders the fully composed config that Compose sees.
Use `--write <path>` if you want to keep the output locally instead of printing it.
Treat the rendered output as potentially secret-bearing.
You can pass several profiles or presets.

## Recommended first deployment flow

```bash
export AOA_STACK_ROOT=/srv/abyss-stack
export AOA_CONFIGS_ROOT=/srv/abyss-stack/Configs

scripts/aoa-doctor
scripts/aoa-install-layout
scripts/aoa-sync-configs
scripts/aoa-bootstrap-configs
scripts/aoa-check-layout --ignore-secrets --strict
scripts/aoa-profile-modules --profile core
scripts/aoa-profile-endpoints --profile core
```

Then create secrets per [SECRETS_BOOTSTRAP](SECRETS_BOOTSTRAP.md).

Then inspect:

```bash
aoa-status --profile core
```

Or manually use the deployed scripts:

```bash
/srv/abyss-stack/Configs/scripts/aoa-up --profile core
```

## Preset example

Bring up a named combined runtime bundle:

```bash
aoa-preset-profiles --preset agent-full --paths
aoa-profile-endpoints --preset agent-full
aoa-render-services --preset agent-full
aoa-up --preset agent-full
```

## Combined runtime example

Bring up an agent runtime plus tools and observability without a preset:

```bash
aoa-profile-modules --profile agentic --profile tools --profile observability --paths
aoa-profile-endpoints --profile agentic --profile tools --profile observability
aoa-up --profile agentic --profile tools --profile observability
```

## systemd user install

After the deployed config tree exists:

```bash
scripts/aoa-install-systemd --enable-now
```

Or manually:

```bash
mkdir -p ~/.config/systemd/user
ln -sf /srv/abyss-stack/Configs/systemd/user/podman-compose-abyss.service ~/.config/systemd/user/podman-compose-abyss.service
systemctl --user daemon-reload
systemctl --user enable --now podman-compose-abyss.service
```

## Safety note

The helper scripts are meant to be boring and explicit.
They should not guess secrets, delete live service data by surprise, or blur the line between checkout paths and runtime paths.
