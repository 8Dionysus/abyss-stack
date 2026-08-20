# Runtime Lifecycle Mechanic

## Mechanic card

Runtime lifecycle is the mechanic for turning source-authored stack shape into
operator-visible runtime behavior without confusing source, deployed mirror, and
live service state.

### Trigger

Use this package when changing install layout, deployment flow, up/down/wait
wrappers, systemd user units, runbook steps, profiles, presets, or service
catalog posture.

### abyss-stack owns

- rootless Podman lifecycle shape
- deployed runtime root and `Configs` mirror expectations
- lifecycle wrapper contracts
- systemd user unit skeletons
- public-safe operator runbook posture

### Stronger owner split

The host OS, Podman, systemd, and `abyss-machine` own their own live facts. AoA
and ToS owner repositories own authored meaning consumed by runtime services.

### Inputs

Source docs, compose profiles and presets, public-safe config, operator intent,
host facts, and deployment sync status.

### Outputs

Dry-run commands, validated lifecycle routes, service start/stop wrappers, and
operator-facing runbook guidance. Package-local status readout contracts may
also describe source-safe runtime log artifacts without claiming they are live.

### Must not claim

- source-only edits are live
- a service is healthy without a live check
- a unit should be enabled or started without explicit operator intent
- runtime lifecycle owns machine provisioning

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [config-projection](../config-projection/README.md) for config material,
[machine-fit](../machine-fit/README.md) for host fit, and
[diagnostic-spine](../diagnostic-spine/README.md) for readiness or truth-goal
checks.

## Active route

Stable operator entrypoints stay in `scripts/`. Runtime-lifecycle
implementation bodies for first-run, layout, start/stop, warmup, wait/smoke,
logs/status, and user-unit helpers live under their owning
`mechanics/runtime-lifecycle/parts/` routes. Runtime cache/usage readout schemas
and examples live in `mechanics/runtime-lifecycle/parts/status-readouts/`, with
regression coverage in `mechanics/runtime-lifecycle/parts/status-readouts/tests/`.
Source/runtime parity now routes through
`mechanics/runtime-lifecycle/parts/config-sync-boundary/docs/SOURCE_RUNTIME_PARITY_PACKET.md`,
and live runtime cutover inspection routes through
`mechanics/runtime-lifecycle/parts/start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md`.
Stack MCP runtime provisioning and its read-only pre-launch integrity check
route through
`scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime` and
`scripts/aoa-install-systemd --verify-abyss-stack-mcp-runtime`; provisioning
mutates only while all three planes are stopped, while verification only compares
deployed source-and-lock and measured runtime identities. The guarded automatic
repair action is deliberately different: it stages under shared operation,
source, and runtime locks while the read plane and non-read consumers remain
available. After verification it records and quiesces the exact active
candidate/internal-effect consumer set, upgrades the operation lock to
exclusive, then enumerates and briefly quiesces the active stack and organ
readers for the atomic swap. Every direct shared-venv consumer is serialized:
recurring maintenance and candidate units hold operation/runtime locks, while
long-lived organ readers retain a runtime lock until that final quiescence. The
loaded Memo/Evals candidate and recurring observation/admission/preflight
fragments are verified against their managed lock-aware sources before repair
may proceed; representative production/bootstrap/fallback organ instances also
prove the loaded template generation. A
dependency or build failure therefore leaves every live plane untouched; a
post-quiesce activation failure restores the previous runtime, every reader,
and every non-read consumer that had been active. Before quiescence, repair issues a
private rollback grant bound to the exact measured content and recorded identity
of the still-running runtime. Only the read contour may consume that grant after
rollback; candidate, internal-effect, and general verification remain strict,
and successful replacement removes the grant. Exact repair-fallback counterparts for
the prior active endpoint set then remain live until admission validates and
commits production; a later admission failure restores that fallback.
Provisioning also creates the separate read/candidate policy audit journals
when absent and never truncates them. Verification checks their regular-file,
non-symlink, private-mode, and bounded-size shape without repairing it. Manual
verification and provisioning check both journals; each sandboxed unit checks
only its explicitly named contour because the opposite journal is intentionally
inaccessible.
Managed launch acquires shared source-projection and runtime locks, repeats the
verification under both, and retains them across `exec`; an applying MCP
Configs sync or runtime replacement therefore requires all three stack MCP
planes to be stopped. Candidate and internal-effect launches additionally hold
the shared operation lock so they cannot enter during the two-phase repair. The
all-user-unit install route creates or validates that private operation lock
before linking and reloading units, so an upgraded sandboxed unit never has to
create it itself.
Provisioning additionally creates the private stack MCP observation directory.
The separately linked observation oneshot and timer use the provisioned venv
to compose current runtime evidence from explicit inputs. They are not enabled
or started by provisioning, and all three planes require the
atomically produced `current.json` before launch.
It also creates the private exact-pilot effect root; it does not stage, approve,
start, or execute an effect.
The same user-unit mechanic owns the Memo/Evals read/candidate lifecycle split:
read instances are filesystem-read-only, candidate services use distinct
credentials and finite write allowlists, and credential provisioning, unit
linking, deployment, start, and consumer registration remain separate actions.
