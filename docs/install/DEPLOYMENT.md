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
- [WINDOWS_BRIDGE](../../mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_BRIDGE.md)
- [WINDOWS_SETUP](../../mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_SETUP.md)
- [WINDOWS_PERFORMANCE](../../mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_PERFORMANCE.md)

## Fastest guided route

If you want the least-friction path, use:

```bash
scripts/aoa-doctor
scripts/aoa-first-run --strict
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

`aoa-first-run --strict` is strict about layout and bootstrapped config presence, but still ignores missing secrets on that first pass by design.

Then create secrets per [SECRETS_BOOTSTRAP](../../mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md).

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

See [MEMO_RUNTIME_SEAM](../../mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md) for the runtime-facing memo mirror, `/memo/*` inspection surfaces, and filesystem-first memo export candidates.
See [EVAL_RUNTIME_SEAM](../../mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md) for the runtime-facing eval mirror, `/evals/*` inspection surfaces, and filesystem-first eval export candidates.
See [PLAYBOOK_RUNTIME_SEAM](../../mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md) for the runtime-facing playbook mirror and `/playbooks/*` activation and composition advisory surfaces.
See [KAG_RUNTIME_SEAM](../../mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md) for the runtime-facing `aoa-kag` mirror, `/kag/*` inspection surfaces, and the `Tree-of-Sophia` handoff companion.

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
scripts/aoa-profile-modules --profile substrate
scripts/aoa-profile-endpoints --profile substrate
```

Then bootstrap real secret-bearing files as described in [SECRETS_BOOTSTRAP](../../mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md).

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

Runs profile-aware post-start model warmup. The canonical `llama.cpp`
local-worker path warms by default when the selected profile includes
`32-llamacpp-inference.yml`. The retained Ollama fallback path warms only when
the selected profile includes `30-local-inference.yml` and
`AOA_OLLAMA_WARMUP_ENABLED=true`.
`aoa-up` calls it automatically, so you usually do not need to invoke it by
hand.

### `scripts/aoa-sync-configs`

Copies repo-managed stack material from the source checkout into `${AOA_CONFIGS_ROOT}`,
including public quest route metadata used by stack validation.
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
For the full machine/runtime parity route, use
[SOURCE_RUNTIME_PARITY_PACKET](../../mechanics/runtime-lifecycle/parts/config-sync-boundary/docs/SOURCE_RUNTIME_PARITY_PACKET.md).
For a live runtime-loop cutover decision, use
[LIVE_RUNTIME_CUTOVER_PACKET](../../mechanics/runtime-lifecycle/parts/start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md)
before any start, stop, restart, systemd, profile, or exposure-changing action.
The scheduled source-rooted mirror canary in `.github/workflows/mirror-canary.yml`
rehearses the same parity flow against a temporary runtime root so source/deployed
drift can surface before operator rollout.
Use `aoa-status --autonomy --json` for the operator-readable control-loop verdict after parity and promoted runtime verify.
When the `federation` profile is active, the same verdict also requires route-api health, closure, and federation layer checks to agree.
When the `federation` profile is not active and federated advisory consumption is disabled, route-api checks should appear as `not_enabled` rather than as hard failures.

### Owner-source package deployment route

For a later operator-controlled move of an owner-reviewed source checkout, use
the runtime-lifecycle [owner-source deployment route](../../mechanics/runtime-lifecycle/parts/deployment-route/README.md).
It is a different route from Configs sync:

- source sync is a non-destructive mirror operation and does not provide an
  atomic package switch;
- the owner-source route requires an external typed admission, an exact clean
  commit/tree, and a same-filesystem preflight;
- it stages a self-contained Git release under a versioned identity, then
  atomically replaces one destination symlink while retaining the predecessor;
- activation and rollback are explicit commands and emit receipts; the route
  does not install dependencies, relink Configs, start services, or prove live
  health.

The route rejects dirty source/destination state, stale or mismatched
admission, incomplete staging, cross-device paths, concurrent deployment, and
predecessor identity drift. Artifact signature/SBOM/provenance admission stays
with `abyss-machine`; this repository must not invent an artifact class for a
source-only owner route.

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
Use `--restart-now` when the unit is already active and you want the newly
written selection to take effect immediately.
Use `--preset` or `--profile` to write an explicit user-unit runtime-selection
drop-in. This is the durable path when the live machine must keep a non-default
runtime shape after boot or `systemctl --user restart`. Repeated flags and
comma-separated forms are both accepted.
Use `--overlay <compose-file>` when a host-local resource or model overlay must
survive reboot and unit restarts. The installer validates each overlay against
the deployed `Configs` tree and writes `AOA_EXTRA_COMPOSE_FILES` into the same
drop-in. Overlay selection must be paired with `--preset` or `--profile` so the
drop-in preserves the full runtime shape.

Use `--all-user-units` after `scripts/aoa-sync-configs` when all allowlisted
working user services should be sourced from the deployed `abyss-stack` mirror.
This links every unit in `systemd/user/managed-units.txt` from
`${AOA_CONFIGS_ROOT}/systemd/user` into `~/.config/systemd/user` and runs
`systemctl --user daemon-reload`. It intentionally does not start, stop,
restart, enable, disable, or mask services.

Use `--system-units` only through a privileged route after the Configs mirror is
synced:

```bash
pkexec /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-install-systemd --system-units
```

That installs root-owned copies of every unit in
`systemd/system/managed-units.txt` into `/etc/systemd/system` and runs
`systemctl daemon-reload`. It intentionally does not start, stop, restart,
enable, disable, or mask services or timers.

If `AOA_FEDERATED_RUN_ENABLED=true` is set in the runtime-secret
`Secrets/Configs/langchain-api.env`, the selected user-unit shape must include
the `federation` profile. Preserve the host's current preset and layer
`--profile federation` unless you intentionally want to change the whole runtime
shape.

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
scripts/aoa-profile-modules --profile substrate
scripts/aoa-profile-endpoints --profile substrate
```

After that capture, `aoa-up`, `aoa-down`, `aoa-render-services`, and `aoa-render-config` automatically honor the latest machine-fit posture unless you explicitly disable it.

Then create secrets per [SECRETS_BOOTSTRAP](../../mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md).

For claim wording after bootstrap, use [TRUTH_SURFACES](../../mechanics/diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md).

When the selected runtime explicitly includes `30-local-inference.yml`, Ollama
warmup stays opt-in. Set `AOA_OLLAMA_WARMUP_ENABLED=true` when the retained
fallback gateway should also warm `qwen3.5:9b` and keep it resident for `30m`
unless the stack restarts or the model is explicitly evicted.

Then inspect:

```bash
aoa-status --profile substrate
```

Or manually use the deployed scripts:

```bash
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-up --profile substrate
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
aoa-profile-modules --profile substrate --profile local-worker --profile tools --profile observability --paths
aoa-profile-endpoints --profile substrate --profile local-worker --profile tools --profile observability
aoa-up --profile substrate --profile local-worker --profile tools --profile observability
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
aoa-profile-modules --profile substrate --profile local-worker --profile federation --paths
aoa-profile-endpoints --profile substrate --profile local-worker --profile federation
aoa-up --profile substrate --profile local-worker --profile federation
```

## systemd user install

After the deployed config tree exists:

```bash
scripts/aoa-install-systemd --enable-now
```

For a host whose live `langchain-api` federated consumer is enabled, preserve
the current host preset and layer the federation profile:

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now
```

For a bounded Intel full-stack route, keep the same preset/profile selection and
persist only the overlays that match the selected services:

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation,reranking --overlay compose/tuning/storage.intel-285h.resource-guard.yml,compose/tuning/intel-worker.thin-host.yml,compose/tuning/federation.thin-host.yml,compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml,compose/tuning/observability.thin-host.yml,compose/tuning/tools.thin-host.yml
```

When the overlays are staged in the user unit, apply them through the guarded
route instead of restarting the stack by hand:

```bash
scripts/aoa-apply-resource-guards --dry-run
scripts/aoa-apply-resource-guards
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
