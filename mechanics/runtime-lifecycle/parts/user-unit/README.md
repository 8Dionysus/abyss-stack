# User Unit

Routes `systemd/user/podman-compose-abyss.service`, the live user-unit
allowlist at `systemd/user/managed-units.txt`, and `scripts/aoa-install-systemd`, with the implementation in
`mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`.

User units must point at runtime paths, not the source checkout.

The OVMS owner route uses `abyss-ovms.container` as a rootless Quadlet plus
loopback and Unix activation sockets. The installer places the Quadlet under
`~/.config/containers/systemd/`; the generated `abyss-ovms.service` owns the
container cgroup with `KillMode=mixed`. The proxy exits after idle, systemd
then stops the unneeded container, and the next real connection repeats
owner cold-load admission. No health or smoke path opens the activation socket.
Before those sockets open, `aoa-up` links and reloads the source-managed user
units, provisions or verifies the rootless Podman secret, and retires only the
current Compose project's legacy `ovms` container. The installer and standalone
auth transaction keep unit linking separate from secret mutation: the canonical
mode-`0600` owner file is created once, verified on later starts, and fails
closed on drift without replacing a value used by a running consumer. The
digest-pinned Quadlet image uses `Pull=missing`, so a fresh host can provision
it on the first owner start without weakening image identity.

The installer also links the source-managed
`podman-compose-abyss.service.d/99-runtime-lifecycle.conf`. Its late ordering
keeps the stack's delegated cgroup, explicit teardown, and non-abort stop
contract effective even when the distribution ships a global user-service
drop-in. Other host-local drop-ins remain untouched.

The OVMS Unix activation socket lives under the private runtime directory
`%t/abyss-stack/ovms-socket/`; admission state lives separately under
`%t/abyss-stack/ovms-admission/`. The Intel `langchain-api` client mounts only
the socket directory read-only, so it can reconnect after socket inode
recreation without reading or mutating the owner admission capability.

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

The allowlist includes a non-startable tombstone for the retired
`aoa-mcp-http@.service`, the
owner-specific `aoa-organ-mcp-read@.service`, the dedicated Memo/Evals
candidate services, and their bundle. Each read template
launches one deployed workspace MCP wrapper with
`AOA_MCP_TRANSPORT=streamable-http` and `AOA_MCP_HOST=127.0.0.1`; package code
still defaults to stdio outside that explicit lifecycle. The tombstone has no
server command or bearer; the read template loads only
`%i-mcp-read-bearer-token` and denies persistent filesystem writes. The
`--provision-mcp-http-auth` route retains only an inactive rollback credential;
provision the owner-distinct Decisions, Memo, Evals, KAG, Session Memory, Stats, Abyss
Machine, and staged ToS corpus
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

Managed MCP starts also execute an exact fail-closed preflight condition. The
event-driven `abyss-mcp-preflight-sweep.path` and
`abyss-mcp-admission-keeper.path` units react to registry, deployment, canary,
credential-manifest, observation, and protocol-status changes; paired timers
run as five-minute backstops. These units only publish private machine-readable
reports. They do not start/restart MCP processes or issue owner proof,
acceptance, or admission. A failed preflight leaves the target inactive with an
expected/observed reason instead of entering a restart loop.

The modern admission timer starts one second after the user manager so expired
cold-start recovery begins before normal interactive work. Admission Keeper
and preflight sweep are ordered after that transaction and disable service
start-rate limiting: a finite burst of atomic registry, canary, and catalog
replacements is allowed to settle instead of leaving their path units in
`unit-start-limit-hit`. Their own work remains lock-bounded and cannot widen
the fixed production fleet.
Independent organ canary pairs use three workers by default during each
bootstrap or production evidence wave. The last-known-good/current order stays
serial within one organ, the complete wave joins before publication, and
`ABYSS_MCP_CANARY_WORKERS=1` is the exact sequential rollback setting.
The timer uses a five-minute recurrence rather than continuously replaying a
failed two-phase transaction. Before bootstrap, the refresh verifies the
measured stack runtime and may delegate a guarded exact-lock reprovision to the
opt-in `abyss-stack-mcp-runtime-repair.service` when it has drifted. This
automatic delegation is denied until the operator persists the reversible
host policy with `aoa-install-systemd --enable-abyss-stack-mcp-auto-repair`;
`--disable-abyss-stack-mcp-auto-repair` removes only that opt-in. The repair
delegation first runs the standalone read-only repair-eligibility verifier. It
proves the source package, bootstrap interpreter, shared locks, the complete
runtime parent chain, every existing observation/admission/orchestration/tasks/
effect path, audit journals, and exact loaded unit topology are safe while
allowing the current read/bootstrap processes to remain active. Repair then
builds and verifies the replacement while the read fleet keeps its shared
runtime locks. The eligibility probe shares the operation lock with known
candidate/internal-effect consumers but still rejects an exclusive provisioner.
Only a fully built replacement may record and quiesce the exact active non-read
consumer set. It first takes the internal-effect request gate exclusively, so
an accepted effect completes rollback and receipt while later requests cannot
reach a worker; only then may it stop that endpoint, upgrade the operation lock
to exclusive, and enumerate and
quiesce active stack and organ readers for the final runtime-lock swap.
Pre-quiescence failures leave every plane active; later failures restore the
prior runtime, every reader, and every non-read consumer that had been active;
the stack peer uses an exact, private, read-only rollback grant. Unsafe source,
operation lock, runtime lock, journal, runtime path, or unit topology still
fails closed without taking the working read fleet down. That topology check
also proves the loaded Memo/Evals candidate and recurring
observation/admission/preflight fragments use both shared locks, so a stale
pre-reload definition cannot run during or be restored after the swap. Loaded
production/bootstrap/fallback organ instances likewise prove their shared
runtime-lock templates.
Successful activation starts exact repair-fallback counterparts for the prior active
endpoint set. Admission removes their private fallback list only after the
production handoff validates, and restores those peers on any later failure.
The all-user-unit route creates or validates the private operation lock before
linking upgraded units.

The separately linked `abyss-mcp-protocol-watch.path` reacts to Codex and
protocol-lab source changes; its hourly timer observes new upstream
specification, SDK, conformance, and Codex identities and evidence TTL. The
watcher writes only `${AOA_STACK_ROOT}/Logs/mcp/protocol-watch`, preserves
immutable private observations, and requires an operator-private mode `0600`
runtime plan before executing a removable lab suite. Missing config is a
visible pending trigger, not permission to improvise. Neither linking nor a
green lab mutates production registration or admission.

Use `aoa-install-systemd --install-mcp-http-codex-client` once for the target
user after the MCP package has been projected into deployed `Configs`. The
action preserves the inactive rollback credential, validates or provisions the
fourteen source-isolated owner-read and two candidate credentials, and adds one
managed Zsh function that
delegates new
interactive Codex launches to the deployed client-side launcher. The named
bearers are inherited only by Codex, the managed Codex binary symlink is
unchanged, and running shells and sessions are untouched. The ToS bearer is
staged only; this route does not create its workspace wrapper, start it, or add
it to the owner bundle.
The launcher treats modern MCP availability as a recoverable dependency. It
checks the exact eleven production units and ports and requests the bounded
modern admission recovery oneshot when a member is absent, but never waits for
that transaction and never refuses to exec Codex because MCP is degraded. This
keeps the operator client available while the boot-time timer and lifecycle
units repair MCP independently. `AOA_MCP_READINESS_SKIP=1` suppresses even the
background request for one diagnostic launch.
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
the runtime identity, copies the bootstrap interpreter into the runtime, and
records a deterministic digest of every installed runtime file and symlink
target. A host interpreter replacement therefore does not mutate an already
published runtime through a venv symlink. Reuse rehashes the environment and a missing
or mismatched content digest forces a guarded rebuild. Read-only verification
also runs isolated stdlib and installed-dependency imports, so an unusable
host-backed Python base cannot pass on the private file digest alone. Generated entry-point
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
