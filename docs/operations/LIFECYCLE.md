# LIFECYCLE

## Canonical lifecycle model

The stack should be operated through explicit profiles, optional presets, and a systemd user entrypoint.

## Deployment preparation

The repository now includes deployment bridge scripts under `scripts/`:
- `aoa-doctor`
- `aoa-install-layout`
- `aoa-sync-configs`
- `aoa-bootstrap-configs`
- `aoa-check-layout`
- `aoa-install-systemd`
- `aoa-first-run`

For Windows-host orchestration through WSL, the repository also includes:
- `aoa.ps1`
- `aoa-doctor-win.ps1`
- `aoa-bootstrap-wsl.ps1`

They help bridge from a source checkout into the deployed runtime tree under `${AOA_STACK_ROOT}`.

## Profile and preset introspection

The repository also includes:
- `aoa-preset-profiles`
- `aoa-profile-modules`
- `aoa-profile-endpoints`
- `aoa-render-services`
- `aoa-render-config`

These helpers make it easy to see what a preset, profile, or profile-combination will activate before you start it.
`aoa-render-services` and `aoa-render-config` are the deeper runtime-truth layer because they come from the composed runtime view rather than just docs or module lists.

You may optionally layer bounded overlays after the canonical module list through `AOA_EXTRA_COMPOSE_FILES` on Linux or `-Overlay` on the Windows bridge.

When `${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json` exists, the wrapper scripts also auto-apply its `validated_settings` and any `recommended_overlays` that actually touch the currently selected services before compose resolution.
Explicit environment variables still win, and you can disable the auto-apply bridge with `AOA_MACHINE_FIT_AUTO_APPLY=false`.

## Human-facing wrappers

The repository also includes these runtime wrappers under `scripts/`:
- `aoa-up`
- `aoa-down`
- `aoa-status`
- `aoa-logs`
- `aoa-smoke`
- `aoa-wait`

They resolve presets and profiles into an ordered compose module list.

On Windows, `pwsh -File scripts/aoa.ps1 <command>` is the host-facing wrapper that forwards into the same Linux command surface.

## Composition layers

You can operate:
- one profile
- several composed profiles
- one or more presets
- presets plus extra profiles

Examples:

```bash
aoa-up --profile substrate
aoa-up --profile substrate --profile workflows
aoa-up --profile substrate --profile local-worker
aoa-up --profile fallback-gateway
aoa-up --profile substrate --profile local-worker --profile tools
aoa-up --profile substrate,local-worker,tools,observability
aoa-up --preset agent-full
aoa-up --preset agent-tools --profile observability
```

The order matters because profile ordering is preserved.
Optional layers such as `tools` and `observability` should usually come after the base profile.
Presets expand before direct `--profile` additions.

Post-start model warmup follows the selected modules. `llama.cpp` warms by
default for local-worker selections. Ollama fallback warmup is disabled unless
the operator sets `AOA_OLLAMA_WARMUP_ENABLED=true`.

## Low-level canonical path

Expected pattern:
- one or more presets and profiles resolve to an ordered profile list
- that profile list resolves to an ordered module list
- machine-fit validated settings are applied next when a current machine-fit record exists and auto-apply is enabled
- compose files are applied in that order, with matching machine-fit recommended overlays first and any explicit bounded extra compose overlays appended after them
- the rendered Compose view is inspectable before launch
- systemd user unit becomes the stable operator entrypoint

## Bootstrap manual pattern

Until wrappers are installed into the live runtime path, the intended manual shape is:

```bash
cd /srv/AbyssOS/abyss-stack/Configs
podman compose \
  -f compose/modules/10-storage.yml \
  up -d
```

Optional modules should be layered explicitly rather than assumed.
Add `-f compose/modules/20-orchestration.yml` only when the optional n8n
workflow layer is intentionally part of the manual run.

## Systemd user surface

A first unit skeleton now lives at:
- `systemd/user/podman-compose-abyss.service`

Its expected deployed location is:
- `~/.config/systemd/user/podman-compose-abyss.service`

It assumes the deployed runtime tree exists under:
- `/srv/AbyssOS/abyss-stack/Configs`

The unit delegates its cgroup and leaves container teardown to the explicit
`aoa-down` route. A launcher failure or stop timeout therefore cannot remove
rootless Podman port helpers while the corresponding containers remain alive.
Persistent observability services use bind state under
`/srv/AbyssOS/abyss-stack/Services/monitoring/`; layout installation must run
before an observability start so Podman can apply each mount's private `:Z`
SELinux label during container creation.
`aoa-install-systemd` links the source-managed
`99-runtime-lifecycle.conf` after distribution-wide user-service drop-ins so
the effective live unit preserves that boundary.

Keep the checked-in unit skeleton generic. Host-local runtime choice belongs in
a drop-in written by `scripts/aoa-install-systemd --preset <name>` or
`--profile <name>`; add `--restart-now` when an already-active unit must pick
up the new selection immediately. If the deployed `langchain-api` federated
consumer is enabled, choose a shape that includes `federation`, such as
`--preset intel-full --profile federation` when the host should keep its
current `intel-full` service shape.

The source tree also carries `systemd/user/managed-units.txt` for the host-local
user services that should be routed through the deployed stack Configs mirror.
After syncing configs, use:

```bash
scripts/aoa-install-systemd --all-user-units
```

That mode links the allowlisted unit files from
`/srv/AbyssOS/abyss-stack/Configs/systemd/user` into
`~/.config/systemd/user` and reloads the user daemon. It does not stop, start,
restart, enable, disable, or mask anything. Existing drop-ins remain host-local
and continue to carry per-machine memory or runtime-selection overrides.

Organ read instances use exact owner credentials; Memo and Evals additionally
use dedicated candidate units. Provision the fourteen read bearers with
`--provision-organ-mcp-read-auth` and the two contour-distinct candidate
bearers with `--provision-organ-mcp-candidate-auth`. These actions do not
start, restart, enable, deploy, or register a consumer. Canary each owner and
policy contour separately; a green read endpoint says nothing about candidate
denial, local-port write confinement, owner acceptance, or another connector.

The stack-owned MCP read and candidate planes require an explicitly
provisioned, source-addressed Python runtime and two persistent policy audit
journals. After linking/reloading their units and while both planes are
stopped, run
`scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime`. It creates
the journal root and empty files only when absent, never truncates existing
records, and leaves start/restart explicit. Each plane writes only its own
bounded hash chain. Stop the affected plane before a reviewed archival
continuity handoff; no live or automatic rotation is part of this lifecycle.

The privileged support allowlist under `systemd/system/managed-units.txt` is
installed separately:

```bash
pkexec /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-install-systemd --system-units
```

That command installs root-owned copies of the allowlisted files into
`/etc/systemd/system` and reloads the system daemon. It does not stop, start,
restart, enable, disable, or mask system services or timers.

## Path note

The wrapper scripts treat the deployed Linux runtime path as distinct from any source checkout path.
This is what makes the repository Fedora-first while still usable from Windows-oriented editing workflows.

Truth progression must stay explicit:

- `source_authored`
- `deployed`
- `trial_proven`
- `live_available`

Do not collapse those states into one word such as "landed".
A source-authored change becomes deployed only after `aoa-sync-configs` updates `/srv/AbyssOS/abyss-stack/Configs`.
The sync-managed boundary includes stack-owned `mcp/` packages and root
`schemas/`; service restart is a separate lifecycle action after parity.
Use `python scripts/validate_stack.py --parity-check` when repo-managed surfaces should match the deployed Configs mirror.

## Profile rule

A profile is a declared set of modules.
A module is a declared concern.
Nothing should start just because it once happened to live in a giant file.
