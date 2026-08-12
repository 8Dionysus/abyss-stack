# systemd user units

This directory stores user-unit skeletons for the deployed runtime.

## Current units

- `podman-compose-abyss.service`
- `abyss-stack-resource-guards-apply.service`
- `aoa-mcp-http@.service`, the non-startable tombstone for the retired
  ambient-Python/shared-bearer route
- `aoa-organ-mcp-read@.service`, the owner-specific, filesystem-read-only
  template for admitted read candidates
- `aoa-organ-mcp-read-bootstrap@.service`, the manual, ten-minute bootstrap
  route used only to obtain the first deployment-bound canary before admission
- `aoa-memo-mcp-candidate.service` and
  `aoa-evals-mcp-candidate.service`, the finite-write candidate contours
- `aoa-mcp-http.service`, the fifteen-process local organ bundle
- `abyss-stack-mcp-read.service`, the stack-owned runtime-observation plane
- `abyss-stack-mcp-read-bootstrap.service`, the equivalent manual bootstrap
  route for the stack-owned read contour
- `abyss-stack-mcp-candidate.service`, the separate non-executing plan-candidate
  plane
- `abyss-stack-mcp-internal-effect.service`, the separately credentialed exact
  read-service restart-and-rollback pilot on port `5439`
- `abyss-stack-mcp-observation.service` and
  `abyss-stack-mcp-observation.timer`, the bounded five-minute observation
  producer and two-minute refresh schedule
- `abyss-mcp-protocol-watch.service`, `.path`, and `.timer`, the removable
  protocol-lab drift/TTL detector with an hourly upstream backstop
- `managed-units.txt` allowlists the host-local user units that can be linked
  from the deployed Configs mirror.

## Expected deployed path

Copy or symlink the unit into:

```text
~/.config/systemd/user/
```

Then reload and enable:

Use the route in [AGENTS](AGENTS.md#install-routes).

The checked-in unit defaults to the conservative `substrate` profile. Host-local
drop-ins should carry richer runtime selection rather than editing the source
skeleton for one machine.

The stack runner delegates its runtime cgroup and uses `KillMode=process`.
`aoa-down` remains the explicit owner of container teardown; a failed or timed
out launcher must not make systemd sweep still-healthy rootless Podman port
helpers from the unit cgroup while their containers continue running.
`TimeoutStopFailureMode=terminate` also keeps a stop timeout from escalating
into the distribution-wide abort policy.
The same settings live in the source-managed late drop-in at
`podman-compose-abyss.service.d/99-runtime-lifecycle.conf`; the installer links
it next to the live unit so a distribution-wide user-service drop-in cannot
override this stack-specific lifecycle boundary.

Prefer the installer route when you need a durable runtime selection:

Use the installer route in [AGENTS](AGENTS.md#install-routes).

That command keeps the checked-in unit generic and writes a host-local drop-in
for the selected preset/profile. It can also persist bounded compose overlays
with `--overlay <compose-file>`, which writes `AOA_EXTRA_COMPOSE_FILES` into the
same drop-in. Preserve the current host preset and layer the `federation`
profile whenever the deployed `langchain-api` federated consumer is enabled.
Pair overlays with an explicit preset or profile so the drop-in always describes
the full intended runtime shape.

## Managed live user units

The same installer can also link every unit named in `managed-units.txt`:

Use the all-user-units route in [AGENTS](AGENTS.md#install-routes).

That mode only links unit files and reloads the user daemon. It does not start,
stop, restart, enable, disable, or mask services. Existing user-unit drop-ins
remain host-local and continue to apply, which lets the stack take ownership of
the unit source path without losing per-machine memory or runtime-selection
overrides. Existing `/dev/null` masks are preserved rather than silently
replaced with source links.

The current allowlist covers the local working surface:

- `podman-compose-abyss.service`
- `abyss-stack-resource-guards-apply.service`, a manual one-shot unit that runs
  `aoa-apply-resource-guards --wait-game-guard-clear` and applies staged cgroup
  limits only after the game guard clears
- the retired `aoa-mcp-http@.service` tombstone, owner-specific
  `aoa-organ-mcp-read@.service`, its manual-only bootstrap template,
  Memo/Evals candidate units, and
  `aoa-mcp-http.service` bundle; these run
  deployed workspace wrappers with explicit authenticated loopback Streamable
  HTTP, preserve each package's tool authority, and reject unauthenticated
  callers before dispatch
- the separate `abyss-stack-mcp-read.service`,
  manual-only `abyss-stack-mcp-read-bootstrap.service`,
  `abyss-stack-mcp-candidate.service`, and
  `abyss-stack-mcp-internal-effect.service` processes; none belongs to the
  shared owner bundle, and each has a disjoint tool catalog, port, scope,
  client identity, and systemd credential; their explicit ports are `5431`,
  `5433`, and `5439`
  because the storage module owns PostgreSQL on `5432`.
  The bootstrap units have no `[Install]` section, never run the registry/catalog
  preflight, conflict with their production peer, use the exact same credential
  and executable binding, set `Restart=no`, and terminate after ten minutes.
  They exist only to break the first-admission cycle: start one manually after an
  exact deployment, issue its signed deployment-bound canary, stop it, build and
  review registry admission, then start the gated production unit. They are not
  a recovery bypass and must never be enabled or left running.
- the credential-free `abyss-stack-mcp-observation.service`, which composes
  only the exact deployment record, private registry projection, committed
  target catalog, named unit state, and an optional typed evidence overlay;
  its timer is linked but never enabled by the installer
- the credential-free protocol watcher, which records exact local/upstream
  identities and runs no child lab without a separate private mode `0600`
  runtime plan; it cannot start, stop, restart, register, or migrate a
  production contour
- warm dictation and TTS services, plus the `gemma4.spark` stack endpoint
  bridge
- TTS keep-warm timer that periodically exercises the protected warm server
  through `abyss-machine resource launch`
- `gemma4.spark` monitor/digest/micro/jobs timers, nervous, process, storage,
  topology, and doctor timers
- `ydotoold.service` for dictation paste support
- AoA closeout and stats path units that watch owner-local receipt surfaces

The `aoa-stats-live-refresh` pair owns only the runtime trigger and the deployed
command route. Its path unit mirrors the receipt surfaces currently admitted by
`aoa-stats`; its service invokes the deployed refresh command without an
explicit registry argument, leaving canonical registry selection with the
sibling owner.

Linking the MCP units does not start them. After source-to-Configs parity is
green, canary one exact `aoa-organ-mcp-read@OWNER.service`, verify its loopback
port and MCP inventory,
then advance to the next owner. The bundle is lifecycle grouping, not a
gateway. Provision the owner-distinct KAG, Stats, Decisions, Memo, Evals,
Session Memory, Abyss
Machine, staged ToS corpus, 4PDA, Telegram, Discord, Course, StackOverflow, and
XDA read bearers with
`scripts/aoa-install-systemd --provision-organ-mcp-read-auth`. Each read unit
loads only `%i-mcp-read-bearer-token`, runs with `ProtectSystem=strict`, and
has no persistent writable path. Neither template places token values in the
unit environment. `tos-corpus` remains outside the bundle until its deployed
workspace wrapper and live canary exist; the staged credential is not an
admission claim.
The six connector instances are inside the source bundle on ports
`5426`-`5428` and `5436`-`5438`; provisioning or bundle membership still does
not prove a live endpoint or owner acceptance.
Provision the distinct Memo/Evals candidate bearers with
`scripts/aoa-install-systemd --provision-organ-mcp-candidate-auth`. Their
dedicated processes use ports `5434` and `5435`, disjoint catalogs, explicit
application root allowlists, and exact systemd write lanes. Read inventory
discovery cannot expand those write lists.
Provision the two non-committed stack-plane credentials separately with
`scripts/aoa-install-systemd --provision-abyss-stack-mcp-auth`. The action is
idempotent and never prints or replaces either value. Linking the units still
does not start them, and the stack MCP services must not be started until the
typed runtime observation exists and source-to-Configs parity is green. No
Codex client registration is installed for these two contours by this action.
Provision their dependency-closed Python environment after sync with
`scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime`. The
source-and-lock-addressed environment lives under
`${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv`; both units refuse activation
through `ConditionPathExists`, an executable `ExecCondition`, and a read-only
runtime verifier when it is absent, unusable, drifted, or no longer matches the
deployed source and hash lock. The verifier recomputes the measured runtime,
including resolved interpreter bytes, before every launch. The final
`ExecStart` then holds the shared source-projection and runtime locks, repeats
the verification under both, and executes the installed server without a
verify-to-launch gap. The verifier opens both lock files read-only so
`ProtectSystem=strict` does not turn the safety check into a write request.
Runtime provisioning, applying MCP Configs sync,
credential provisioning, unit linking, start, and client registration remain
separate actions.
That runtime provision action also creates the persistent policy journals at
`${AOA_STACK_ROOT}/Logs/mcp/audit/policy-read.jsonl` and
`policy-candidate.jsonl` without truncating existing evidence. Both units
require the safe `0700/0600` path shape before launch. Under
`ProtectSystem=strict`, each process receives one exact writable journal and
an inaccessible path for the opposite contour; the contour-explicit unit
verifier checks only the visible journal and rejects a policy-family mismatch,
while provisioning and unsuffixed manual verification check both journals.
Startup validates the complete bounded hash chain before bind.
The same provision action creates the private
`${AOA_STACK_ROOT}/Logs/mcp/observations` directory. It does not create a live
claim. Start `abyss-stack-mcp-observation.service` once to atomically produce
`current.json`; all stack MCP contour and bootstrap units refuse to start
without it.
Provisioning also creates the private non-symlink
`${AOA_STACK_ROOT}/Logs/mcp/admission/keeper-inbox` directory. The admission
keeper consumes independently issued `(organ_id)/(contour_id)/*.json` nodes
from that root; provisioning neither issues nor copies owner evidence.
`abyss-mcp-admission-keeper.path` lists every consumed contour directory from
the runtime target catalog explicitly because `systemd.path` does not watch
nested file replacement recursively; the periodic timer remains the bounded
backstop for missed or coalesced events.
The modern admission timer starts one second after the user manager. Keeper
and preflight services are ordered behind that transaction and allow finite
publication bursts without becoming permanently failed through
`unit-start-limit-hit`.
Enable `abyss-stack-mcp-observation.timer` only as a separate reviewed rollout
step. Its process has no bearer credential, no network address family, and no
writable path outside that observation directory.
Provisioning installs the exact artifact-hashed lock, binds the bytes behind
the resolved venv interpreter into the runtime-content digest, and refuses to
replace a changed environment while any stack MCP unit is active or its
state cannot be observed; it never stops a plane implicitly.
The lifetime locks mean an applying MCP Configs sync and changed runtime
provisioning fail closed while any plane is active; stop all three planes
explicitly before sync or reprovisioning. The units execute the installed venv
module, not the mutable `Configs/src` tree, clear inherited `PYTHONHOME` and
`PYTHONPATH`, invoke Python in isolated mode, and pass `-B` explicitly. Neither
a Configs sync nor ambient user-manager imports can replace the measured module
closure, and service imports cannot write bytecode that invalidates its
recorded digest. Rerun runtime provisioning before a later restart.

The units intentionally consume host-owned commands such as `abyss-machine`
instead of copying host-layer implementation into `abyss-stack`.

For the current Gemma 4 E2B shape, `abyss-stack` owns the live `llama-cpp`
serving endpoint at `http://127.0.0.1:11435`. The host `gemma4.spark`
controller and timers consume that endpoint for evidence, digest, micro, and
jobs artifacts. Keep `abyss-gemma4-spark.service` and
`abyss-gemma4-spark.timer` disabled in stack-owned mode so they do not launch a
second host-local `llama-server`.

System-wide support units have a separate privileged route under
[`../system`](../system/README.md).

## Assumption

The unit expects the deployed runtime tree to exist under:
- `/srv/AbyssOS/abyss-stack/Configs`
