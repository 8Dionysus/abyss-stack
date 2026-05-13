# DEPLOYMENT

This document explains how a source checkout becomes a deployed Fedora-first runtime tree.

## Core distinction

The source checkout and the deployed runtime tree are not the same thing.

Typical shape:
- source checkout anywhere convenient
- deployed runtime at `/srv/AbyssOS/abyss-stack`
- optional heavy-data vault at `/abyss`

A GitHub checkout of this repository is a source/install mirror, not a backup of
live runtime state. It should contain portable source material and public-safe
templates only. Real `Secrets/`, `Logs/`, `Models/`, live `stack.env`, rendered
compose output, local databases, model binaries, and private captures are
created outside git through `scripts/aoa-install-layout`,
`scripts/aoa-sync-configs`, and `scripts/aoa-bootstrap-configs`.

If you are operating from a Windows host through WSL, also read:
- [WINDOWS_BRIDGE](../mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_BRIDGE.md)
- [WINDOWS_SETUP](../mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_SETUP.md)
- [WINDOWS_PERFORMANCE](../mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_PERFORMANCE.md)

## Fastest guided route

If you want the least-friction path, use:

```bash
scripts/aoa-doctor
scripts/aoa-first-run --strict
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

`aoa-first-run --strict` is strict about layout and bootstrapped config presence, but still ignores missing secrets on that first pass by design.

Then create secrets per [SECRETS_BOOTSTRAP](../mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md).

If you want the optional `federation` profile, sync the public-safe `aoa-agents` contract pack, the `aoa-routing` advisory pack, the `aoa-memo` recall pack, the `aoa-evals` eval-selection pack, the `aoa-playbooks` advisory pack, the `aoa-kag` derived retrieval pack, and the source-owned `tos-source` handoff companion after bootstrap:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
```

See [MEMO_RUNTIME_SEAM](../mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md) for the runtime-facing memo mirror, `/memo/*` inspection surfaces, and filesystem-first memo export candidates.
See [EVAL_RUNTIME_SEAM](../mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md) for the runtime-facing eval mirror, `/evals/*` inspection surfaces, and filesystem-first eval export candidates.
See [PLAYBOOK_RUNTIME_SEAM](../mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md) for the runtime-facing playbook mirror and `/playbooks/*` activation and composition advisory surfaces.
See [KAG_RUNTIME_SEAM](../mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md) for the runtime-facing `aoa-kag` mirror, `/kag/*` inspection surfaces, and the `Tree-of-Sophia` handoff companion.

## Scenario A: Fedora-native source checkout

Example:
- source checkout at `~/src/abyss-stack`
- deployed runtime at `/srv/AbyssOS/abyss-stack`

Suggested flow:

```bash
cd ~/src/abyss-stack
scripts/aoa-doctor
scripts/aoa-install-layout
scripts/aoa-sync-configs
scripts/aoa-bootstrap-configs
scripts/aoa-check-layout --ignore-secrets --strict
scripts/aoa-sync-federation-surfaces --layer aoa-agents   # optional federation contract mirror
scripts/aoa-sync-federation-surfaces --layer aoa-routing  # optional federation advisory mirror
scripts/aoa-sync-federation-surfaces --layer aoa-memo     # optional federation memo mirror
scripts/aoa-sync-federation-surfaces --layer aoa-evals    # optional federation eval mirror
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks  # optional federation playbook mirror
scripts/aoa-sync-federation-surfaces --layer aoa-kag      # optional federation KAG mirror
scripts/aoa-sync-federation-surfaces --layer tos-source   # optional Tree-of-Sophia handoff mirror
scripts/aoa-profile-modules --profile core
scripts/aoa-profile-endpoints --profile core
```

Then bootstrap real secret-bearing files as described in [SECRETS_BOOTSTRAP](../mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md).

## Scenario B: Windows checkout plus Linux runtime

Example:
- source checkout on Windows host at `D:\src\abyss-stack`
- Linux runtime inside WSL2 or a Podman-oriented Linux layer at `/srv/AbyssOS/abyss-stack`

Suggested logic:
1. keep editing in the Windows checkout if that is convenient
2. use `pwsh -File scripts/aoa.ps1 host-doctor` and `pwsh -File scripts/aoa.ps1 doctor --preset agent-full` from PowerShell to validate the host bridge
3. run the deployment bridge scripts inside the Linux layer against the repo view available there, either directly or through `pwsh -File scripts/aoa.ps1 ...`
4. deploy into `/srv/AbyssOS/abyss-stack`
5. bootstrap public-safe runtime config files from templates
6. bootstrap secrets separately
7. optionally map a Windows host vault path into `/abyss`

The important thing is not where the source lives.
The important thing is that the deployed runtime still becomes `/srv/AbyssOS/abyss-stack` inside Linux.

## What the helper scripts do

### `scripts/aoa-doctor`

Checks host-side and runtime-side readiness for the Fedora-first model.
It reports missing commands, platform mismatches, vault mount state, and Intel-specific hints such as `/dev/dri` presence.
Use `--strict` if warnings should fail the command.

From a Windows host, use `pwsh -File scripts/aoa.ps1 host-doctor` for the Windows+WSL readiness pass before invoking the Linux doctor.

### `scripts/aoa-machine-fit`

Captures the bounded current-machine runtime posture after the layout exists.
Use it to record:
- which preset this host should currently prefer
- whether the relevant host packages are current in configured repos
- what validated local tuning should be reused
- whether the current host envelope is too noisy for latency-sensitive work

### `scripts/aoa-install-layout`

Creates the non-destructive runtime directory skeleton under `${AOA_STACK_ROOT}`.
It does not delete existing data.

### `scripts/aoa-warmup`

Warms the local Ollama chat model after startup when the selected profile includes `30-local-inference.yml`.
`aoa-up` calls it automatically, so you usually do not need to invoke it by hand.

### `scripts/aoa-sync-configs`

Copies repo-managed stack material from the source checkout into `${AOA_CONFIGS_ROOT}`.
By default it is non-destructive.
An explicit `--delete` mode exists for a tighter mirror when that is desired.
This is the boundary where a source-authored change becomes deployed.
A source-authored change is not live until `scripts/aoa-sync-configs` updates `/srv/AbyssOS/abyss-stack/Configs`.

After syncing repo-managed surfaces, run:

```bash
python scripts/validate_stack.py --parity-check
scripts/aoa-status --autonomy --json
```

to confirm the canonical source checkout still matches the deployed `Configs` mirror for repo-managed paths.
The scheduled source-rooted mirror canary in `.github/workflows/mirror-canary.yml`
rehearses the same parity flow against a temporary runtime root so source/deployed
drift can surface before operator rollout.
Use `aoa-status --autonomy --json` for the operator-readable control-loop verdict after parity and promoted runtime verify.
When the `federation` profile is active, the same verdict also requires route-api health, closure, and federation layer checks to agree.
When the `federation` profile is not active and federated advisory consumption is disabled, route-api checks should appear as `not_enabled` rather than as hard failures.

The shortest honest verify path for the current promoted runtime is:

```bash
python scripts/validate_stack.py
python scripts/validate_stack.py --parity-check
python /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60
bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --autonomy --json
```

### `scripts/aoa-bootstrap-configs`

Copies public-safe config templates and source-managed helper-service build contexts into the runtime tree if the destination files are missing.
Use `--force` only when you explicitly want template content to overwrite existing runtime config files.
`--force` also refreshes existing runtime helper-service trees from `config-templates/Services/`.

The agent-facing runtime may also consume a public-safe return policy file at `${AOA_STACK_ROOT}/Configs/agent-api/return-policy.yaml`, bootstrapped from `config-templates/`.
The same bootstrap path now carries `${AOA_STACK_ROOT}/Configs/agent-api/governed-execution-policy.yaml` for the first governed mutation lane.
It now also carries `${AOA_STACK_ROOT}/Configs/agent-api/governed-canary-catalog.json` for bounded real-task request seeding.
The route-first ToS graph helper now also uses `${AOA_STACK_ROOT}/Configs/tos-graph/config.yaml`, a runtime-only `${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env`, `${AOA_STACK_ROOT}/Logs/tos-graph/`, the source-owned `AOA_TOS_ROOT` mount for the real `Tree-of-Sophia` checkout, and a read-only mount of `${AOA_STACK_ROOT}/Configs/stack.env` so it can reuse `NEO4J_AUTH` without duplicating live credentials.
When that template changes and the deployed runtime should consume the refreshed policy, run `scripts/aoa-bootstrap-configs --force` after `scripts/aoa-sync-configs`.
The governed execution packet root lives at `${AOA_STACK_ROOT}/Logs/governed-runs/`, and the operator entrypoint is `scripts/aoa-governed-run`.

### `scripts/aoa-check-layout`

Checks the runtime tree and reports missing directories, missing template-derived config files, and missing secret-bearing files.
Use `--ignore-secrets` for the first bootstrap pass before secrets exist.
Use `--strict` if warnings should fail the command.
When the `federation` profile is selected, it also checks the mirrored `aoa-agents` contract pack under `${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents`, the mirrored `aoa-routing` advisory pack under `${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing`, the mirrored `aoa-memo` recall pack under `${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo`, the mirrored `aoa-evals` eval-selection pack under `${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals`, the mirrored `aoa-playbooks` advisory pack under `${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks`, the mirrored `aoa-kag` retrieval/regrounding pack under `${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag`, and the source-owned `tos-source` handoff pack under `${AOA_STACK_ROOT}/Knowledge/federation/tos-source`.

### `scripts/aoa-sync-federation-surfaces`

Copies a small allowlisted subset of public-safe sibling-repo surfaces into the deployed runtime tree.
The current landing slice supports:

- `--layer aoa-agents`
- `--layer aoa-routing`
- `--layer aoa-memo`
- `--layer aoa-evals`
- `--layer aoa-playbooks`
- `--layer aoa-kag`
- `--layer tos-source`

The mirror targets for these layers are:

- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents`
- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing`
- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo`
- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals`
- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks`
- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag`
- `${AOA_STACK_ROOT}/Knowledge/federation/tos-source`

For closure-aware operator checks on an active federation seam, prefer:

```bash
scripts/aoa-sync-federation-surfaces --check --json --layer aoa-routing
scripts/aoa-status --autonomy
```

Rendered compose truth and deployed autonomy readiness are different layers.
`aoa-render-config` tells you what Compose sees; `aoa-status --autonomy` tells you whether the promoted `llama.cpp + LangGraph + route-api` control loop is currently coherent on the deployed path.

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

If you need to layer a bounded overlay, use `AOA_EXTRA_COMPOSE_FILES` on Linux or `-Overlay` with `scripts/aoa.ps1` on Windows.
If a current private machine-fit record exists, the wrappers also auto-apply its `validated_settings` and only those `recommended_overlays` that touch the selected services unless `AOA_MACHINE_FIT_AUTO_APPLY=false`.

## Recommended first deployment flow

```bash
export AOA_STACK_ROOT=/srv/AbyssOS/abyss-stack
export AOA_CONFIGS_ROOT=/srv/AbyssOS/abyss-stack/Configs

scripts/aoa-doctor
scripts/aoa-install-layout
scripts/aoa-sync-configs
scripts/aoa-bootstrap-configs
scripts/aoa-check-layout --ignore-secrets --strict
python scripts/validate_stack.py --parity-check
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
scripts/aoa-sync-federation-surfaces --layer aoa-agents   # optional
scripts/aoa-sync-federation-surfaces --layer aoa-routing  # optional
scripts/aoa-sync-federation-surfaces --layer aoa-memo     # optional
scripts/aoa-sync-federation-surfaces --layer aoa-evals    # optional
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks  # optional
scripts/aoa-sync-federation-surfaces --layer aoa-kag      # optional
scripts/aoa-sync-federation-surfaces --layer tos-source   # optional
scripts/aoa-profile-modules --profile core
scripts/aoa-profile-endpoints --profile core
```

After that capture, `aoa-up`, `aoa-down`, `aoa-render-services`, and `aoa-render-config` automatically honor the latest machine-fit posture unless you explicitly disable it.

Then create secrets per [SECRETS_BOOTSTRAP](../mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md).

For claim wording after bootstrap, use [TRUTH_SURFACES](../mechanics/diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md).

For local-Ollama profiles, `aoa-up` also performs a post-start warmup of `qwen3.5:9b` and keeps the model resident for `30m` unless the stack restarts or the model is explicitly evicted.

Then inspect:

```bash
aoa-status --profile core
```

Or manually use the deployed scripts:

```bash
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-up --profile core
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

Bring up an agent runtime plus the optional federation seam:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
aoa-profile-modules --profile agentic --profile federation --paths
aoa-profile-endpoints --profile agentic --profile federation
aoa-up --profile agentic --profile federation
```

## systemd user install

After the deployed config tree exists:

```bash
scripts/aoa-install-systemd --enable-now
```

Or manually:

```bash
mkdir -p ~/.config/systemd/user
ln -sf /srv/AbyssOS/abyss-stack/Configs/systemd/user/podman-compose-abyss.service ~/.config/systemd/user/podman-compose-abyss.service
systemctl --user daemon-reload
systemctl --user enable --now podman-compose-abyss.service
```

## Safety note

The helper scripts are meant to be boring and explicit.
They should not guess secrets, delete live service data by surprise, or blur the line between checkout paths and runtime paths.
