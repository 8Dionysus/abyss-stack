# User Unit

Routes `systemd/user/podman-compose-abyss.service`, the live user-unit
allowlist at `systemd/user/managed-units.txt`, and `scripts/aoa-install-systemd`, with the implementation in
`mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`.

User units must point at runtime paths, not the source checkout.

The installer also links the source-managed
`podman-compose-abyss.service.d/99-runtime-lifecycle.conf`. Its late ordering
keeps the stack's delegated cgroup, explicit teardown, and non-abort stop
contract effective even when the distribution ships a global user-service
drop-in. Other host-local drop-ins remain untouched.

`aoa-install-systemd --preset <name>`, `--profile <name>`, and
`--overlay <compose-file>` write a small runtime-selection drop-in next to the
linked unit. Add `--restart-now` when the unit is already active and the new
selection should take effect immediately. Repeated flags and comma-separated
forms both write the same comma-separated systemd environment value.
Use that path for durable host-local choices such as
`--preset intel-full --profile federation --overlay compose/tuning/storage.intel-285h.resource-guard.yml`;
do not bake machine-specific profile selection or resource overlays into the
source unit skeleton.
Overlay selection must be paired with a preset or profile so replacing the
drop-in cannot silently clear the runtime shape.

When `Secrets/Configs/langchain-api.env` enables the federated live consumer,
the selected user-unit shape must include the `federation` profile so
`route-api` survives the next systemd start.

Use `aoa-install-systemd --all-user-units` to link every source-managed user
unit from the deployed Configs mirror into `~/.config/systemd/user`. This is a
link-and-reload operation only; it preserves enable state, running processes,
host-local drop-ins, and existing `/dev/null` masks.

The allowlist includes `aoa-mcp-http@.service` and its bundle. The template
launches one deployed workspace MCP wrapper with
`AOA_MCP_TRANSPORT=streamable-http` and `AOA_MCP_HOST=127.0.0.1`; package code
still defaults to stdio outside that explicit lifecycle. It also loads the
non-committed `aoa-mcp-http-bearer-token` systemd credential; package startup
fails before bind if the credential is missing or invalid. Provision it only
through the explicit `aoa-install-systemd --provision-mcp-http-auth` action,
which never prints or replaces an existing valid value. A missing secret root
is created with mode `0700`; an existing root keeps its current permissions,
and symlinked roots or credential files fail closed. Install never starts or
restarts an owner. Canary and restart each instance separately after
source/deployed parity so one failed owner cannot hide behind bundle state.

Use `aoa-install-systemd --install-mcp-http-codex-client` once for the target
user after the MCP package has been projected into deployed `Configs`. The
action validates or provisions the same credential and adds one managed Zsh
function that delegates new interactive Codex launches to the deployed
client-side launcher. The bearer is inherited only by Codex, the managed Codex
binary symlink is unchanged, and running shells and sessions are untouched.
`--remove-mcp-http-codex-client` removes only that managed Zsh block.

The stack-owned read and non-executing candidate planes have separate
credentials provisioned by
`aoa-install-systemd --provision-abyss-stack-mcp-auth`. First creation uses an
atomic no-clobber publication step, so concurrent installers keep and validate
one winner rather than replacing each other. Their managed Python environment
is a separate explicit action:
`aoa-install-systemd --provision-abyss-stack-mcp-runtime`. It installs the
artifact-hashed dependency lock, binds deployed source and lock digests into
the runtime identity, and refuses to replace a changed environment while
either plane is active or its user-systemd state cannot be observed. It never
stops or starts those units implicitly. Run `--all-user-units` first so the
loaded unit definitions participate in the runtime lock. Each plane then holds
a shared lock for its full process lifetime; changed provisioning takes the
exclusive lock and repeats the stopped-state check immediately before the
environment swap, closing starts that race the build.

Use `pkexec .../aoa-install-systemd --system-units` for the small privileged
support-unit allowlist under `systemd/system/`. That mode installs root-owned
copies into `/etc/systemd/system`, reloads the system daemon, and deliberately
does not start, stop, restart, enable, disable, or mask units.
