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
scripts/aoa-sync-federation-surfaces --check --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
```

The routing line is deliberately check-only. The stable
`Knowledge/federation/aoa-routing/` namespace is materialized from an admitted
`aoa-sdk` release only through receipt-bound
`scripts/aoa-routing-cutover materialize`; ordinary federation sync has no
routing source checkout and cannot repair that mirror.

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
scripts/aoa-sync-federation-surfaces --check --layer aoa-routing  # optional federation advisory mirror
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
including stack-owned runtime MCP packages, their root contract schemas, and
public quest route metadata used by stack validation.
By default it is non-destructive.
An explicit `--delete` mode exists for a tighter mirror when that is desired.
This is the boundary where a source-authored change becomes deployed.
A source-authored change is not live until `scripts/aoa-sync-configs` updates `/srv/AbyssOS/abyss-stack/Configs`.
This applies to MCP service code as well: user units execute the package
entrypoints under `Configs/mcp`, while deployed decision-graph validation reads
`Configs/schemas`.

Preview the exact bounded projection before a lifecycle-sensitive rollout:

```bash
scripts/aoa-sync-configs --dry-run --item mcp --item schemas --item systemd --item scripts --item mechanics
scripts/aoa-sync-configs --item mcp --item schemas --item systemd --item scripts --item mechanics
scripts/aoa-install-systemd --all-user-units
scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime
scripts/aoa-install-systemd --provision-mcp-http-auth
scripts/aoa-install-systemd --provision-organ-mcp-read-auth
scripts/aoa-install-systemd --provision-organ-mcp-candidate-auth
scripts/aoa-install-systemd --provision-abyss-stack-mcp-auth
# Produce one bounded live observation before starting either stack MCP plane:
systemctl --user start abyss-stack-mcp-observation.service
# Enable recurrence only after reviewing that first observation:
systemctl --user enable --now abyss-stack-mcp-observation.timer
# First admission only: manually start the bounded bootstrap peer. It has no
# install target, never restarts, conflicts with production, and exits after
# ten minutes. Do not enable it.
systemctl --user start aoa-organ-mcp-read-bootstrap@aoa-kag.service
# The canary binds the exact latest deployment manifest and does not admit a
# consumer or start/stop a unit itself:
/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/venv/bin/abyss-stack-mcp-canary \
  --organ aoa-kag --process-unit bootstrap
# Materialize and review the transitional overlay/catalog while the exact
# signed bootstrap process is still live:
systemctl --user start abyss-mcp-admission-keeper.service
systemctl --user stop aoa-organ-mcp-read-bootstrap@aoa-kag.service
# After reviewing managed-contours.json and its preflight result, use only the
# normal preflight-gated unit:
systemctl --user start aoa-organ-mcp-read@aoa-kag.service
# Replace the transitional bootstrap receipt with evidence bound to the exact
# production PID/start identity before proof, acceptance, or admission:
/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/venv/bin/abyss-stack-mcp-canary \
  --organ aoa-kag
# Later standalone rotation, only with every stack MCP plane and bootstrap stopped:
scripts/aoa-install-systemd --rotate-abyss-stack-mcp-auth
scripts/aoa-install-systemd --install-mcp-http-codex-client
```

`--item` is repeatable and accepts only the public-safe managed allowlist;
unknown items and `Secrets` fail closed. `--dry-run` requires an existing
target and never mutates it. Source-control, bytecode, and test/tool caches are
excluded from deployment. The systemd installer links and reloads only,
preserves existing masks, and does not start or restart the newly linked MCP
owners. The legacy provision action creates the transitional shared bearer
under `Secrets/Configs` without printing or replacing it. The organ read
provision action creates owner-distinct read credentials for `aoa-decisions`,
`aoa-memo`, `aoa-evals`, `aoa-kag`, `aoa-session-memory`, `aoa-stats`,
`abyss-machine`, `tos-corpus`, `aoa-4pda-connector`,
`aoa-telegram-connector`, `aoa-discord-connector`,
`aoa-course-connector`, `aoa-stackoverflow-connector`, and
`aoa-xda-connector`, rejects equal values, and publishes only their digests in
a secret-local manifest. The candidate provision action also creates distinct
`aoa-memo` and `aoa-evals` candidate credentials and verifies that all sixteen
owner/contour values differ. Codex entries use matching named variables:
`AOA_DECISIONS_MCP_READ_BEARER_TOKEN`,
`AOA_MEMO_MCP_READ_BEARER_TOKEN`, `AOA_EVALS_MCP_READ_BEARER_TOKEN`,
`AOA_KAG_MCP_READ_BEARER_TOKEN`,
`AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN`,
`AOA_STATS_MCP_READ_BEARER_TOKEN`, `ABYSS_MACHINE_MCP_READ_BEARER_TOKEN`, or
`TOS_CORPUS_MCP_READ_BEARER_TOKEN`, with exact connector-specific variables
for all six connector packages. The ToS credential is staged for a later
wrapper/canary admission; it does not add that owner to the bundle. The legacy
compatibility template continues to name `AOA_MCP_HTTP_BEARER_TOKEN`. No value
may be copied into `config.toml`.

Memo and Evals candidate services use ports `5434` and `5435`, distinct
candidate variables, disjoint tool catalogs, and source-enumerated application
plus systemd write allowlists. Provisioning, linking, package deployment,
starting, and client registration remain separate actions.
The authenticated canary is likewise separate: it reads one owner-specific
credential, observes the exact loopback MCP schema and structured read result,
checks the committed result contract, then emits a private secret-free receipt
and a separate private content-addressed result artifact for owner review.
It does not stop or start services,
rewrite Codex registration, merge production evidence, infer freshness or
grounding/acceptance, run an owner reviewer, or change registry admission.
Course, StackOverflow, and XDA use `5436`, `5437`, and `5438`, preserving the
stack MCP ports `5431`/`5433` and PostgreSQL reservation `5432`.

An applying sync that includes `mcp` additionally requires a clean exact Git
revision. After rsync it compares the complete source and deployed MCP service
trees and each package, including modes, versions, entrypoints, and dependency
locks. Each package entry also binds the exact source revision. Exact parity
publishes one immutable content-addressed record under
`${AOA_STACK_ROOT}/Logs/mcp/deployments/records/` and atomically refreshes
`latest.json`. Drift or symlinks make the sync non-zero and issue no new exact
receipt. This deployment manifest proves only source-to-`Configs` package
parity; it explicitly leaves process, endpoint, registry, consumer schema,
grounded result, acceptance, admission, and rollback unobserved.

The stack MCP provision action creates distinct read and non-executing
candidate credentials; neither credential is shared with the owner adapters or
with the other stack contour. Existing equal values are rejected without
printing them. It does not register either service with Codex
and does not start a unit. Start remains a later canary decision after the
typed runtime observation, deployed parity, and consumer contract are ready.
Both managed stack MCP units treat loopback as locality rather than identity:
bearer scope remains mandatory, and the unit sandbox denies non-loopback IP
traffic while leaving the two loopback listeners available.
Credential rotation is an explicit standalone operation. It refuses active or
unobservable stack MCP units, changes both contour credentials and their
digest manifest without printing values, and never restarts a process. Refresh
the registered consumers before the subsequent sequential canary.
The stack MCP runtime provision action builds a source-addressed virtual
environment under `${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv` from the
already deployed package, installs its exact hash-locked dependency closure,
verifies dependencies and imports, records both source and lock digests, and
copies the bootstrap interpreter into the published runtime so a later host
interpreter replacement cannot mutate the measured closure through a symlink.
It also records a deterministic digest of the installed runtime files, symlink
targets, and bytes behind the fully resolved `bin/python` chain after rebinding
generated entry-point shebangs from the private staging path to the stable
published venv path. It does not link, stop, start, or register a service.
Repeating it against the same deployed package and lock rehashes the installed
environment and reuses it only when that digest still matches; missing or
changed runtime bytes force the same guarded rebuild path. A changed
runtime identity fails closed while either stack MCP unit is active or its
user-systemd state cannot be observed; stop both planes explicitly before
reprovisioning. Each plane holds shared source-projection and runtime locks for
its full lifetime; changed provisioning takes the exclusive runtime lock and
repeats the stopped-state check immediately before swapping the environment.
The preceding
`--all-user-units` link-and-reload step is required so every later start
participates in that lock; combining it with runtime provisioning in one
installer invocation is rejected. Provisioning installs only from a private
snapshot whose package and lock digests match the initial deployed tree, then
rehashes deployed source before publishing the runtime identity and swapping
the environment. It holds a source-projection lock from before its first
deployed-source read through the swap; an applying MCP Configs sync holds the
same exclusive lock for its full rsync transaction. Either command fails
closed rather than crossing the other's publication boundary.
Provisioning also creates a private observation directory. The distinct
credential-free observation oneshot verifies the immutable deployment record,
private registry source, committed owner-specific target catalog, and exact
named user-unit fields before atomically writing a five-minute observation.
It does not scan sibling workspaces, read a bearer, call an owner endpoint, or
infer the missing source digest, consumer schema, freshness, proof, acceptance,
canary, or rollback axes. Its two-minute timer is linked but remains disabled
until the operator explicitly enables it after reviewing the first result.
Shared-bearer compatibility units are excluded instead of being relabelled as
owner-isolated processes.
The Codex client install adds a removable Zsh launch function that delegates
to the deployed launcher without replacing the managed Codex executable or
exporting the bearer into the parent shell. It affects only new interactive
shell launches and leaves running Codex sessions unchanged. If the modern MCP
fleet is incomplete, the launcher requests background admission recovery and
starts Codex immediately; MCP lifecycle failure never blocks the operator
client. The boot timer retries at a five-minute cadence, and the refresh may
invoke the guarded runtime-repair oneshot before its exact bootstrap handoff.
Verify parity, then canary authenticated owners one at a time before using live
MCP responses as current evidence.

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

### `scripts/aoa-routing-canary`

This is not the ordinary federation sync route. It consumes an exact
`aoa-sdk` routing candidate only after `abyss-machine` has admitted the
specific source ref and subject digest for `runtime_canary`.

Rehearse into a new isolated target first:

```bash
scripts/aoa-routing-canary materialize \
  --isolated \
  --subject-store /absolute/subject-store/root \
  --trust-verdict /absolute/durable/trust-gate.json \
  --target-root /absolute/isolated/aoa-routing-canary \
  --sdk-source-ref SDK_GIT_OBJECT_ID \
  --predecessor-source-ref AOA_ROUTING_GIT_OBJECT_ID \
  --subject-digest sha256:SUBJECT_DIGEST
```

Run `check` with the same exact-input flags before any operator review.
An existing target is never overwritten without a disjoint sibling
`--rollback-root`. The live route additionally requires
`--authorized-live-canary` and a named `--operator-change-ref`; it is valid
only for a target ending in `Knowledge/federation/aoa-routing`.

Rollback is explicit and recoverable:

```bash
scripts/aoa-routing-canary rollback \
  --authorized-live-canary \
  --target-root /srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-routing \
  --rollback-root /srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-routing.pre-sdk-canary \
  --candidate-retain-root /srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-routing.sdk-canary-retained \
  --sdk-source-ref SDK_GIT_OBJECT_ID \
  --predecessor-source-ref AOA_ROUTING_GIT_OBJECT_ID \
  --subject-digest sha256:SUBJECT_DIGEST \
  --operator-change-ref OWNER_CHANGE_RECORD_ID
```

Rollback does not require the subject store or trust-verdict file: their
revocation, loss, or canary corruption must not prevent predecessor restore.
It records whether the displaced candidate identity was still inspectable.
The command never starts route-api, never declares G5, and never turns
`canary_ready` into ordinary `closure_ready`. Live activation and service
restart remain separate operator-reviewed actions.

### `scripts/aoa-routing-cutover`

This is the distinct, receipt-bound G5 route. Merging or deploying the script
does not change producer authority. Use it only after the SDK has published an
exact canonical artifact whose materialized subject store contains
`succession/routing-g5-owner-switch.json`, and `abyss-machine` has admitted
that exact receipt and artifact for `runtime`.

Rehearse the exact cutover inputs into an isolated target:

```bash
scripts/aoa-routing-cutover materialize \
  --isolated \
  --subject-store /absolute/canonical-subject-store/root \
  --trust-verdict /absolute/durable/runtime-trust-gate.json \
  --owner-switch-receipt /absolute/canonical-subject-store/root/succession/routing-g5-owner-switch.json \
  --target-root /absolute/isolated/aoa-routing-g5 \
  --sdk-source-ref SDK_GIT_OBJECT_ID \
  --predecessor-source-ref AOA_ROUTING_GIT_OBJECT_ID \
  --subject-digest sha256:CANONICAL_SUBJECT_DIGEST
```

Run `check` with the same exact-input flags. The separately reviewed live
mutation replaces `--isolated` with `--authorized-live-cutover` and requires
both a disjoint sibling `--rollback-root` and a named
`--operator-change-ref`. It is valid only for the deployed target ending in
`Knowledge/federation/aoa-routing`. The command first fsyncs a validated,
durable prepared stage, then fsyncs the common parent after each tree rename.
A repeated exact command validates and continues a prepared, between-renames,
or already-activated state, so interruption never requires a manual rename.

Rollback is explicit:

```bash
scripts/aoa-routing-cutover rollback \
  --authorized-live-cutover \
  --target-root /srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-routing \
  --rollback-root /srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-routing.pre-sdk-g5 \
  --canonical-retain-root /srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-routing.sdk-canonical-retained \
  --sdk-source-ref SDK_GIT_OBJECT_ID \
  --predecessor-source-ref AOA_ROUTING_GIT_OBJECT_ID \
  --subject-digest sha256:CANONICAL_SUBJECT_DIGEST \
  --operator-change-ref OWNER_CHANGE_RECORD_ID
```

Runtime rollback restores predecessor bytes as a compatibility posture; it
does not reverse SDK source ownership and does not authorize repository
archival. Before the swap, the command verifies the rollback tree's manifest,
exact predecessor ref, stable ABI identity, and every configured file hash.
It persists
`manifest/routing_g5_compatibility_rollback.json` in the restored tree, so
route-api keeps reporting `compatibility_rollback_active` and non-closing
posture after restart. If either atomic swap step fails, the exact staged
marker is removed from the rollback root so that the already-verified
predecessor remains retryable. If the process terminates instead, a repeated
command validates and recovers the exact marker-before-swap, between-swap, or
already-restored state; the last case returns idempotent success. Route-api
may report normal closure only for an `authorized_live_cutover` while the
exact `sdk_canonical` receipt, typed producer-admission trust controls,
public-release record, subject bytes, and mirror hashes agree. Malformed
control collections remain non-ready instead of raising a health error. An
isolated rehearsal remains non-closing. The marker file is fsynced before its
rename, its directory is fsynced afterward, and the common tree parent is
fsynced after every rollback rename.

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

Use `--provision-abyss-stack-mcp-auth` before canarying the stack-owned MCP
read or candidate process. It creates separate read and candidate bearer
credentials under `${AOA_STACK_ROOT}/Secrets/Configs`, keeps each file at mode
`0600`, is idempotent, and never prints or replaces a valid existing value.
It also compares the resulting values and fails closed if read and candidate
would share one bearer.
Use `--rotate-abyss-stack-mcp-auth` later as a standalone operation with every
managed plane and the read bootstrap stopped. It rotates all three credentials
and the binding manifest together,
does not print values or restart units, and requires consumer refresh before
the next sequential canary.
This action grants no runtime-effect authority: the candidate process only
compiles an expiring content-addressed plan with
`execution_authorized=false`.

Use `--provision-abyss-stack-mcp-runtime` after syncing the MCP package and
after `--all-user-units` has linked and reloaded the lock-aware units, but
before canarying either stack-owned plane. It must run as the target user,
installs the deployed package and the exact `requirements.lock` closure with
artifact-hash enforcement into
`${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv`, verifies `pip check` and
runtime imports, and records a runtime identity containing both the exact
deployed-package digest and lock digest, plus a deterministic digest over the
installed runtime files, symlink targets, and fully resolved interpreter bytes.
It also creates, without truncation, separate read and candidate policy audit
journals under `${AOA_STACK_ROOT}/Logs/mcp/audit`, enforces directory mode
`0700`, file mode `0600`, regular non-symlink files, and the managed 32 MiB
per-contour capacity. The read-only verifier requires this safe path shape; the
server validates the complete receipt hash chain before bind.
Generated console-script shebangs are rebound to the stable published venv
before that digest and the atomic rename, so no launcher retains the removed
staging path. Reuse requires the observed runtime digest to match that recorded
value; otherwise provisioning rebuilds under the same lock and stopped-plane
guards. If the source-and-lock identity
changes while either
`abyss-stack-mcp-read.service` or `abyss-stack-mcp-candidate.service` is
active, or when their user-systemd state cannot be observed, the action refuses
to mutate the environment; stopping and later starting those units remain
explicit operator actions. The units hold a shared lock for their whole
process lifetime and also retain the shared source-projection lock.
Provisioning takes the exclusive form of the runtime lock and rechecks both
unit states after the build, immediately before the environment swap, so a
concurrent start cannot cross the replacement boundary. Do not combine this
flag with `--all-user-units`; the installer rejects that ordering.
The package and hash lock are copied to a private digest-matched snapshot and
pip reads only that snapshot. The deployed tree is rehashed before the marker
and swap. Provisioning holds the same source-projection lock that an applying
MCP Configs sync holds across its full rsync transaction, so the deployed
source and published runtime identity cannot pass each other between recheck
and environment replacement.
The user units point only at this environment and use `ConditionPathExists`,
an executable `ExecCondition`, and a contour-explicit
`--verify-abyss-stack-mcp-runtime=read|candidate` as a read-only second
condition. Each unit checks only its own audit journal because systemd
intentionally makes the opposite contour inaccessible. The unsuffixed manual
verification and runtime provisioning still check both journals. Before every
launch the unit verifier recomputes the deployed source-and-lock identity and
the measured runtime-content digest, including resolved interpreter bytes, so
a missing, unusable, drifted, or source-mismatched runtime leaves the unit
inactive instead of entering a restart loop.
The final `ExecStart` acquires the shared source-projection lock followed by
the shared runtime lock, repeats the verifier under both, and `exec`s the
server while retaining both locks for the process lifetime. The verifier opens
both lock files read-only, so this guard remains compatible with
`ProtectSystem=strict`; only sync and provisioning open them for mutation.
Applying MCP
Configs sync and changed provisioning therefore fail closed while either plane
runs; stop both planes explicitly before sync or reprovisioning, then start
them only after both operations and their parity checks succeed.
They clear ambient `PYTHONHOME`/`PYTHONPATH`, invoke that venv in isolated
Python mode with explicit bytecode writes disabled, and execute its installed
package rather than importing `Configs/src` or an inherited user-manager
module. After a later stopped-plane Configs sync, rerun this provision action
before starting or restarting either plane.
Each unit can write only its own exact journal path and cannot access the
opposite contour journal. Capacity exhaustion fails closed. Automatic
rotation is not installed; stop the affected plane and use a reviewed archive
continuity handoff rather than truncating or replacing a live journal.

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
scripts/aoa-sync-federation-surfaces --check --layer aoa-routing  # optional
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
scripts/aoa-sync-federation-surfaces --check --layer aoa-routing
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
