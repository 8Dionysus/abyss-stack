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

The allowlist includes the transitional `aoa-mcp-http@.service`, the
owner-specific `aoa-organ-mcp-read@.service`, the dedicated Memo/Evals
candidate services, and their bundle. Each read template
launches one deployed workspace MCP wrapper with
`AOA_MCP_TRANSPORT=streamable-http` and `AOA_MCP_HOST=127.0.0.1`; package code
still defaults to stdio outside that explicit lifecycle. The transitional
template loads `aoa-mcp-http-bearer-token`; the read template loads only
`%i-mcp-read-bearer-token` and denies persistent filesystem writes. Provision
the former with `--provision-mcp-http-auth` and the owner-distinct Decisions,
Memo, Evals, KAG, Session Memory, Stats, Abyss Machine, and staged ToS corpus
read credentials, plus the exact 4PDA, Telegram, Discord, Course,
StackOverflow, and XDA connector read credentials, with
`--provision-organ-mcp-read-auth`.
Provision the Memo/Evals candidate credentials with
`--provision-organ-mcp-candidate-auth`; it verifies that all fourteen read and
two candidate values are distinct.
Provisioning never prints or replaces an existing valid value, rejects
owner-equal read tokens, and writes only a secret-local digest manifest. A
missing secret root is created with mode `0700`; symlinked roots or credential
files fail closed. Install never starts or restarts an owner. Canary and
restart each instance separately after source/deployed parity so one failed
owner cannot hide behind bundle state.

Use `aoa-install-systemd --install-mcp-http-codex-client` once for the target
user after the MCP package has been projected into deployed `Configs`. The
action validates or provisions the legacy credential plus the fourteen
source-isolated owner-read and two candidate credentials and adds one managed Zsh function that
delegates new
interactive Codex launches to the deployed client-side launcher. The named
bearers are inherited only by Codex, the managed Codex binary symlink is
unchanged, and running shells and sessions are untouched. The ToS bearer is
staged only; this route does not create its workspace wrapper, start it, or add
it to the owner bundle.
The candidate values remain separate named variables for separate Memo/Evals
candidate registrations; inheriting them does not merge endpoint authority.
`--remove-mcp-http-codex-client` removes only that managed Zsh block.

The stack-owned read and non-executing candidate planes have separate
credentials provisioned by
`aoa-install-systemd --provision-abyss-stack-mcp-auth`. First creation uses an
atomic no-clobber publication step, so concurrent installers keep and validate
one winner rather than replacing each other; equal read/candidate values are
rejected after both files are validated. Explicit rotation uses
`aoa-install-systemd --rotate-abyss-stack-mcp-auth` as a standalone action. It
first proves both managed planes are stopped, replaces both credentials and
their digest manifest without printing values, leaves the units stopped, and
requires consumer refresh before a canary start. A partial publication remains
fail-closed because startup verifies each bearer against the final manifest.
Their managed Python environment
is a separate explicit action:
`aoa-install-systemd --provision-abyss-stack-mcp-runtime`. It installs the
artifact-hashed dependency lock, binds deployed source and lock digests into
the runtime identity, and records a deterministic digest of every installed
runtime file and symlink target. Reuse rehashes the environment and a missing
or mismatched content digest forces a guarded rebuild. Generated entry-point
shebangs are rewritten from the private staging root to the stable published
venv path before this digest is recorded and before the atomic rename. Bytecode writes are
disabled while provisioning, verifying, and running the managed units so the
measured closure remains stable. Replacement is refused while either plane is
active or its user-systemd state cannot be observed. It never stops or starts
those units implicitly. Run `--all-user-units` first so the loaded unit
definitions participate in the runtime lock. Each plane then holds a shared
lock for its full process lifetime; changed provisioning takes the exclusive
lock and repeats the stopped-state check immediately before the environment
swap, closing starts that race the build. Linking and provisioning in one
invocation is rejected. The environment is installed only from a private
source-and-lock snapshot that matches the initial deployed digest, and deployed
source is rehashed before marker publication and swap. A separate exclusive
source-projection lock is held from before the first deployed-source read
through the environment swap; an MCP Configs sync takes the same lock around
its full rsync transaction, so neither publication can cross the other's
commit boundary.
Pre-launch verification opens both lock files read-only and takes shared locks,
so it remains valid inside `ProtectSystem=strict`; mutation paths keep their
exclusive read/write lock ownership.
The same runtime provision action creates two persistent, non-truncated policy
audit journals under `${AOA_STACK_ROOT}/Logs/mcp/audit`: `policy-read.jsonl`
and `policy-candidate.jsonl`. The root is mode `0700` and files are mode
`0600`; symlinks, non-regular files, broad modes, or files beyond the managed
32 MiB bound fail closed. Verification does not create or repair these paths.
Each managed unit can write only its own exact journal path and hides the
opposite contour. Its pre-launch and launch verifier therefore names and checks
only that unit's contour, while the unsuffixed manual verifier and provisioning
continue to check both journals. The launch contour must match
`ABYSS_STACK_MCP_POLICY_FAMILY`. Stop a plane before any reviewed archive
handoff; no automatic journal rotation is installed.

Use `pkexec .../aoa-install-systemd --system-units` for the small privileged
support-unit allowlist under `systemd/system/`. That mode installs root-owned
copies into `/etc/systemd/system`, reloads the system daemon, and deliberately
does not start, stop, restart, enable, disable, or mask units.
