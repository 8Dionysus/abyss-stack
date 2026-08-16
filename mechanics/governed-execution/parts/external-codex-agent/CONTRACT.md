# External Codex Agent Runtime Contract

## Owner split

- `aoa-sdk` owns the model-neutral `RunPlan`, the post-compile incarnation
  binding shape, canonical digests, and cross-object validation.
- `aoa-agents` owns role and mandate meaning.
- `aoa-models` owns model identities, realizations, scoped claims, studies,
  and fit projections.
- `abyss-stack` owns this launch protocol, tool profiles, process/session
  lifecycle, runtime state, normalized events, resume, effect observation, and
  runtime result.
- `aoa-evals` owns comparison packets and verdict meaning.
- the target owner and the user retain acceptance and all external effects.

The runtime may reject a binding. It may not silently select or substitute a
model, reasoning effort, role, tool surface, permission ceiling, task, or wake
policy.

## Invocation

Production callers bind an installed compatible `aoa-sdk` explicitly:

```text
<absolute-python> -I <absolute external_codex_agent.py> <operation> \
  --state-root <absolute-state-root> ...
```

`scripts/aoa-external-codex-agent` is a source-checkout convenience. Its
shebang is not proof of the SDK ABI used in production.

The machine-local installed contour instead uses one content-addressed release
containing the exact controller, neutral launch binder, supervisor, study
preparer, schemas, runtime profile, `aoa_sdk` package, SDK-owned
incarnation/summon schema closure, and the runtime-profile-pinned
`aoa-agents` owner execution request plus `aoa-skills` task-local DAG schemas.
The installer must recompute those two owner-schema digests and match the
profile pins before packaging them.
The packaged SDK root must therefore satisfy both isolated imports and the
preparer's exact non-Python contract reads. Each stable wrapper is a minimal
static x86_64 Linux ELF with no `PT_INTERP`; it filters every `LD_*` variable
before the first dynamic executable and executes its own embedded bootstrap
through fixed `/usr/bin/python3 -I -B`. That payload binds the exact
`active.json` digest compiled into the already-running ELF and never opens an
adjacent companion pathname. Installation, activation, and status compile and
validate that launcher from the packaged assembly through fixed
`/usr/bin/cc`. The companion consults a regular-file active receipt, verifies
and seals every manifest file, and materializes those descriptors at the
namespace-private `/mnt/aoa-external-codex-release` inside one read-only
bubblewrap tmpfs. The host release coordinate is used only for descriptor-based
verification and is never reused as the runtime import coordinate. Imports,
packaged data, and self-digest reads must resolve inside that snapshot, never
by reopening a verified host pathname. Wrappers also disable bytecode writes
so ordinary execution cannot add `__pycache__` entries to its own immutable
release. They do not follow a mutable source checkout, import ambient
`PYTHONPATH`, or use a symlinked `current` directory.
For rollback compatibility only, activating an immutable legacy release whose
verified manifest predates the packaged assembly may build the same validated
launcher from the current landed installer source. A newly materialized
release must carry and build its own manifest-bound assembly.
The selected and recorded Python coordinate must
be a direct ELF CPython 3.11-or-newer executable at install, activation, and
status time. Its compatibility probe must execute that same admitted inode;
script and executable delegate shims are not admissible. Executable-bit
presence alone is not admission. Before packaging, every selected source file hidden by
assume-unchanged or skip-worktree and every ignored selected file must make its
owner checkout dirty, with the classified path set counted and digested in the
receipt. Such bytes require the matching explicit dirty-source admission and
must never be represented as a clean production source posture.
After materialization and before wrapper or active-receipt mutation, the
installer re-enumerates every selected input, requires all four Git posture
snapshots to remain exact, and re-hashes every source byte against the release
manifest. A checkout or byte race may leave an unactivated content-addressed
release, but it cannot publish a falsely attributed active release.
For a host-admitted canary, `stage` stops at that immutable release and a
read-only staged record; it must not publish wrappers or `active.json`.
`activate-admitted` then recomputes the artifact-subject aggregate from the
exact release manifest and invokes the named non-symlink `abyss-machine`
executable with fixed `runtime_canary`, `abyss-stack`, exact source-ref,
host-managed trust-root, registry, and subject-digest arguments. Activation
requires an allow-or-warn decision with no blocker or manual-review residue,
the selected record still latest, the subject store present, all declared
controls verified, and every source/content/record identity bound. The gate
receipt is preserved in the active record. An ordinary `activate` is rollback
compatibility only and carries no artifact-admission claim.
`install_external_codex_runtime.py status`
requires the release tree to contain exactly the manifest files and their
necessary parent directories, rejects every symlink or extra entry, and
re-hashes the release, rebuilds and validates the static launcher, and verifies
each launcher/companion pair before availability may be claimed.
Activation rollback changes only the active receipt while retaining immutable
releases. An install, status, or activation target is admitted only as an exact
SHA-256 release ID whose resolved directory and manifest identity remain one
direct child of the configured release root.

Operations are:

- `aoa-external-actor-bind --manifest <absolute json> --output <absolute launch>`
  binds already owner-selected artifacts and starts nothing;
- `preflight --launch <absolute launch.json>`;
- `start --launch <absolute launch.json>`;
- `run-to-terminal --launch <absolute launch.json>`;
- `status|events|result --session-id <exact session id>`;
- `interrupt --session-id <exact session id>`;
- `resume --session-id <exact session id> --resume-request <absolute json>`;
- `yield-parent --obligation <absolute json>`;
- `reenter-parent --reentry-id <exact re-entry id> --child-result <absolute json>`;
- `reentry-status --reentry-id <exact re-entry id>`;
- `export-a2a-result` with exact writer/reviewer sessions, summon request, and
  output path.

The operator-visible incarnation launcher has a separate lifecycle contour for
the responsibility holder. `launch --holder-receipt <absolute json>` is valid
only for the direct `exec` route (not detached Kitty): immediately before the
Codex `exec`, it writes a non-replacing receipt containing the holder PID,
process-parent PID/start ticks, the first Kitty ancestor PID/start ticks/argv,
the detached Kitty window identity/dedication proof, and executable/manifest
digests. The holder argv is the post-exec `/proc` shape, including the
interpreter argv of a shebang-backed executable. This receipt is not a governed
proof-actor result and must not be substituted with a nested actor's runtime
identity. The Kitty-ancestor binding covers the installed bubblewrap wrapper as
well as a direct host exec while retaining one exact terminal identity; the
holder environment must bind `KITTY_PID` and `KITTY_WINDOW_ID`, and no sibling
terminal child may remain outside the holder lineage and Kitty helper
processes. After a wake bridge has recorded confirmed handoff delivery, the
installed launcher may run `close --holder-receipt ... --wake-receipt ...
--handoff ... --closure-receipt ...`; before selecting a signal target it
requires the handoff to bind the exact holder receipt path, receipt digest,
holder/terminal PIDs, and reserved closure path under
`runtime.responsibility_holder`. A producer must not leave the closure path
only under a live-proof projection. The wake receipt also carries the SHA-256
of the exact handoff bytes delivered to the master; the closer hashes and
parses that same snapshot before accepting delivery. It then rechecks the holder's exact
kernel boot ID and PID/start-ticks/argv, its process-parent identity, the recorded Kitty window,
and the dedicated Kitty process, reserves the closure receipt before
signaling in a recoverable, atomically published sidecar reservation. The
sidecar is locked and advanced to a durable signal-attempt state before the
first `TERM`; each state transition is an atomic replacement under a separate
stable lock inode, recovery rechecks the completed receipt after lock
acquisition, and never sends a second `TERM` for an existing attempt. The
final receipt is also published as one complete non-replacing file, and a
completed `closed: false` receipt remains a failure on replay. Every atomic
publication fsyncs both the complete file and its containing directory before
lifecycle code can proceed, so recovery sees the reservation/attempt entry
rather than a merely cached directory update. Direct launch copies the exact
verified executable bytes into a sealed immutable snapshot, keeps that
descriptor inheritable across a shebang interpreter exec, and executes the
snapshot rather than mutable source-inode bytes or a reopened pathname. It then
sends `TERM` to the exact holder process
through a pidfd opened after the final identity check; the receipt records that signal target
separately from the terminal it observes. The non-replacing closure receipt
records the final Kitty disappearance
independently and is written even when closure is unverified. If delivery is
proven but both exact identities have naturally disappeared before the closer
runs, it records the successful non-signaling `already_gone` outcome without
reopening or reconstructing the incarnation marker. A host-side wake route
may own the bridge and closer in one same-user systemd unit so wake delivery,
closure, and after-inventory remain ordered even when the visible actor is
the terminal being closed. Ambiguous, reused, or drifted identities fail
closed.

Each CLI call writes one `abyss_stack_external_codex_response_v1` JSON object.
`start` returns after the independent worker is durably recorded; later calls
observe the persisted session. If a caller stops after the exact `prepared`
state is durable but before any worker attempt exists, a later `start` with the
same launch digest retries that launch. The forked worker remains behind a
one-byte pipe gate and exits on EOF; it cannot form a Codex process group until
the parent has durably recorded its PID and start ticks. The later bubblewrap
mount gate uses a Unix socket whose peer endpoint is retained by bubblewrap via
`--sync-fd`: only an explicit byte releases `--block-fd`, while supervisor EOF
cannot. Immediately before writing that byte, the supervisor again requires the
exact worker PPID and no pending termination signal. An abort additionally keeps
the supervisor endpoint open until the gated wrapper is killed and reaped.
`run-to-terminal` starts the same durable
session but keeps the caller alive until one runtime-owned semantic terminal
state is recorded. It is the compatible entry point for transient service
launchers whose cgroup is torn down when their main process exits. Its polling
cadence is observation only and imposes no execution timeout or budget.

## Exact admission

Before launch the controller verifies:

1. every launch coordinate is absolute and its delivered bytes match the
   launch digest;
2. the plan snapshot and plan digest are current, and the incarnation binding
   names that exact plan;
3. task, role, model realization, runtime profile, result schema, workspace,
   immutable inputs, permissions, tools, observe-only usage metering, continuation, and wake
   identities match across their owner objects;
4. task correlation, continuation, and expected incarnation IDs match the
   binding without relying on filenames;
5. the model realization names Codex CLI `0.147.0`, ChatGPT quota/login,
   `exec-jsonl`, one admitted model/effort, and the exact runtime tool profile;
6. the resolved Codex executable digest, reported version, auth status, and
   bundled live model catalog match the binding;
7. the exact profile-bound Linux subreaper supervisor and probe executable are
   available, a disposable parent-death/subreaper containment probe succeeds,
   and the exact Codex executable successfully constructs its inner named
   sandbox through the outer read-only mount-mask contour before inference;
8. the workspace is an exact Git worktree at the pinned HEAD and requested
   clean/exact baseline, selected by one explicit immutable manifest input ID;
9. every additional immutable input is pinned by the continuation and copied
   into the private runtime state before the model sees it;
10. every task validation command ID is unique, and the final report covers the
   exact fixed command sequence with a non-empty evidence reference for every
   passed, failed, or skipped claim; each claimed status must equal the final
   runtime-observed exit state of an exact argv execution;
11. the task carries the complete runtime-wide forbidden-effect set; terminal
    classification applies that same set independently of task input;
12. `transport_study_fixture` is admitted only as bounded compatibility
    evidence and may retain historical SDK incarnation binding v1 receipts.
    `owner_contour` additionally requires a separate exact `aoa-agents`
    `summon-request-v4`, validated against its runtime-profile-pinned owner
    bytes, plus SDK incarnation binding v2. Their obligation, mandate, exact
    role resolution, informational model-fit query and chosen projection,
    exact model realization and SDK run plan, ready task-local DAG, accepted
    responsibility transfer, domain procedure refs, child scope,
    external-process/session posture, and observe-only usage
    semantics must match the launch and continuation exactly. Owner semantic
    self-digests and immutable transport-byte digests remain distinct and both
    are verified. The terminal runtime result identifies the admitted owner
    request by its stable `request_ref` and the digest of the exact admitted
    bytes, rather than by the runtime-private materialization path. That
    materialized immutable snapshot remains a separate path-addressable
    `evidence_refs` member for runtime recovery and continuation closure.
    Runtime state v4 owns this representation. A pre-upgrade v3 state instead
    requires the exact historical path-shaped `owner_admission_ref`, including
    the same admitted byte digest and evidence membership. Result reads,
    recovery, resume, reviewer preparation, review-seed issuance, and initial
    parent re-entry accept that legacy form only when the durable state is v3;
    v4 cannot downgrade and v3 cannot claim the stable v4 form. The
    discriminator is not the mutable state version or any closure of
    session-local files. Every newly
    admitted owner-contour launch contains
    `owner_admission_identity_mode=stable_request_ref_v1`, and the owner
    request binds the digest and object identity of those exact launch bytes.
    Before first state publication the controller also publishes one
    non-replacing, mode-0400 generation anchor under the state-root-level
    `owner-admission-generations/` ledger. It binds session, launch, exact
    launch bytes, exact owner-request bytes, stable request identity, identity
    mode, and provenance outside the rewriteable session directory. Every
    later owner-result read must agree with that anchor. Its same-UID pathname
    is not treated as immutable: absence always fails closed. The only route
    that may recreate a missing legacy anchor is additionally authorized by an
    exact pre-upgrade inventory sealed into the verified content-addressed
    release. The launcher verifies that catalog and mounts it from a sealed
    memfd in the read-only runtime snapshot; a session created after the
    inventory cannot add itself to the migration set. Supplying a non-empty
    inventory is a staging operation only. Ordinary `install` rejects a
    catalog-bearing source, and ordinary `activate` rejects a catalog-bearing
    staged release. Only `activate-admitted`, after the host artifact trust gate
    has bound the complete release manifest and catalog bytes, may publish its
    `active.json` and wrappers.
    A legacy v3 receipt is accepted only when its materialized launch lacks
    that mode and the request's semantic self-digest plus `runtime_launch_ref`
    still bind the same launch and an explicit operator migration has matched
    its session, launch, request, and stable request identity against that
    release-bound catalog before publishing a legacy-generation anchor.
    Unanchored v3 state fails closed; ordinary reads never infer or create a
    migration record. The marker is mandatory for a new owner-contour
    admission. An anchored markerless launch may pass preflight or start only
    when an existing durable v3 session has the same launch digest,
    owner-admission digest, materialized request, and legacy generation. This
    permits reviewed recovery from a crash after durable `prepared` state but
    before attempt one without reopening legacy admission or allowing a v4
    session to manufacture its own downgrade.
    A current-generation crash after anchor publication but before first state
    publication is also retryable: the same launch/request identity reuses the
    anchor timestamp, only an unpublished actor projection whose baseline bytes
    still match the digest held by that external anchor may be reused, and at
    most one exact prepared event with the anchored timestamp may be reconciled
    into first state. Because same-UID mode bits are not a trust boundary, the
    projection must also match a fresh one-time witness materialized directly
    from the admitted source or exact review seed; the witness is removed by
    its pinned inode before recovery continues. New admissions therefore
    publish a v2 anchor. Stable-request v1 anchors were never deployed and are
    rejected rather than treated as historical compatibility; actual legacy
    v3 sessions enter only through the release-cataloged explicit migration
    above, which also publishes a v2 anchor. No Git command runs against the mutable
    recovered projection. All non-index Git bytes must match the safe witness,
    whose private-Git authority is captured in memory before its staging inode
    receives a public session pathname; later mutation of the published witness
    cannot alter that comparison value. The recovered index is copied from a
    pinned descriptor into a sealed memfd, and only its stage/flag meaning is
    interpreted against the fresh witness with hooks and fsmonitor disabled.
    The recovered content and private Git body are inventoried again after that
    inspection. Any mismatch fails closed without executing a concurrently
    introduced repository config, attribute, hook, fsmonitor, or filter.
    The same binding is checked after first-state publication: every durable
    v2 state must retain the anchor-bound baseline reference and bytes. If the
    state is still `prepared` with no attempt, the independent source/seed
    witness is rebuilt before the first worker is retried. This recovery path
    accepts current v2 anchors and catalog-authorized legacy-v3 migrations; it
    cannot be entered by relabeling either as a v1 anchor.

The two request-shaped objects are intentionally not collapsed. The
`AgentIncarnationBinding.task_request_ref` is the canonical schema-valid SDK
`summon-request-v4` typed scenario artifact and must be used by an active C2
step. The richer runtime-owner `external-codex-task` remains a separate exact
runtime constraint, pinned by the plan snapshot and continuation and matched
to the delivered task bytes. The task also carries the summon request and its
exact SDK schema as immutable inputs. This preserves SDK transport meaning
without asking the generic summon schema to own runtime paths, validation
commands, permission scope, stop policy, or return-owner meaning.

The study preparer does not hard-code a Sol/Luna sequence. It accepts only the
non-empty unique arm order fixed by the exact `aoa-models` study and requires
the delivered realization list to match that order exactly.

The runtime revalidates its read-only materialized plan/binding/task/profile
and immutable input bytes on every worker entry. Durable state is itself
schema-validated on every load and save.

The admitted owner coordinate remains the canonical report schema. At session
creation, the controller materializes one private derivative whose added
constraints are exact `const` values for the task and incarnation IDs plus an
exact allowlist of the materialized immutable-input identities in finding and
transition evidence references. Source and controller-owned runtime evidence
retain their canonical reference shapes. The derivative's path and digest are
persisted in runtime state and revalidated before inference, after inference,
and during A2A export; drift fails closed. This prevents a known runtime
identity or forwarded immutable input from being mistyped or plausibly aliased
in an otherwise substantive report without weakening the post-output semantic
identity and byte checks.

## Process and tool boundary

The argv uses `codex exec`/`codex exec resume`, structured JSONL, a strict final
schema, explicit model and effort, `approval_policy=never`, an explicit cwd and
sandbox, `--ignore-user-config`, `--ignore-rules`, `--strict-config`, and
`--disable multi_agent`. The child inherits only an allowlisted non-secret
environment; secret-shaped variable names are excluded again from the Codex
shell environment. A profile-bound specialized environment is injected through
an explicit `shell_environment_policy.set` map after validation; the runtime
does not widen baseline inheritance beyond `core`. No TUI or built-in
`spawn_agent` surface participates.

Every inference attempt receives a runtime-generated named Codex permission
profile rather than the undifferentiated `-s workspace-write` shortcut. Before
the worker or model starts, the controller materializes a fresh runtime-owned
actor projection of the admitted exact Git-worktree baseline, rejecting
unsupported special entries or unsafe symlinks. It copies content through open
directory/file descriptors and constructs a private `.git` body from the exact
admitted HEAD and index objects; private Git config, remotes, alternates, logs,
and source coordinates are excluded. It records a source
manifest before and after materialization and fails closed if those source
bytes or directory identities differ. Projection staging is created and
renamed relative to one pinned parent descriptor. The authoritative baseline is
built from the retained staging descriptor before publication; the public
coordinate is published with non-replacing `renameat2`, and must then name the
same device/inode. Rename commitment is recorded before post-publication
verification, so cleanup uses the pinned parent descriptor and exact staged
inode even when verification fails. Cleanup is identity-bound and
refuses a replaced coordinate, producing typed contaminated admission instead
of deleting an unowned tree. The actor baseline, final manifest, and
canonical before/after delta are durable session artifacts. The projection is
the only model target, cwd, validation root, and mutable repository surface;
the source checkout remains the owner acceptance surface and is never passed
as a model coordinate. A reviewer may clone an exact writer projection only
from a controller-issued envelope binding the terminal writer session, result,
final manifest, delta, source manifest, and projection. The envelope is
recomputed under the writer lock, and reviewer immutable evidence must bind the
same writer duty. Neither review preparation nor execution needs the historical
source checkout after the writer has returned.

Controller-original immutable inputs and actor inputs are separate authority
surfaces. The actor receives only
`abyss_stack_external_codex_actor_input_envelope_v1`: JSON payloads are parsed,
source and ancestor coordinates are removed structurally from mapping keys as
well as values, and post-sanitization key collisions fail closed. Text is
sanitized through bounded nested JSON string-escape decoding, including mixed
literal/escaped text, escaped slashes, hex-case variants, and surrogate pairs;
excessive escape depth fails closed. Binary payloads whose byte shadow contains
a literal or JSON-escaped source coordinate are rejected before reversible
base64 materialization. The same decoded alias check runs after serialization. The same
complete alias set is projected out of model-facing role, task, continuation,
validation, and resume control views without rewriting runtime-owned paths to
already-sanitized envelopes. Every
derivative is validated against its own schema and digest. The original bytes
remain controller-only for A2A and closeout. A non-review source is canonicalized
once during admission; workspaces beneath Codex's built-in minimal-read system
roots are rejected, and the controller-original directory is explicitly denied
to the child permission profile.

UTF-8 text redaction uses decoded layers only as matching views. Each matched
literal or escaped alias is mapped back to its exact original character span
before replacement, so unrelated bytes—including literal backslash escapes,
newlines, and slash spellings—remain unchanged. The same bounded mapping covers
literal, Unicode-escaped, slash-escaped, mixed, and nested source aliases.

The projection receives sanitized actor-local Git configuration, network remains
disabled, and the attempt-local scratch area is separate. The worker opens the
projection with `O_PATH|O_DIRECTORY|O_NOFOLLOW`, inventories the open inode,
passes a duplicate descriptor through the supervisor/mount launcher, and asks
bubblewrap to bind that descriptor at the fixed child-only coordinate
`/tmp/aoa-external-actor-workspace`. The worker retains its original descriptor
through terminal inventory. Closeout verifies that the durable host pathname
still names the same device/inode and fails closed on replacement. Command
observation still classifies explicit Git config/config-lock operands and
generic `.git` writers as counterevidence; this classification does not turn
the old mount launcher into a pathname-race proof.

On an unprivileged host, bubblewrap realizes this filesystem contour with a
user namespace plus a mount namespace. It adds no outer PID or network
namespace and no role authority. Codex 0.147 must still create its own inner
bubblewrap/private-PID sandbox; failure to do so rejects the runtime contour.

Semantic profiles admit only `read-only` or bounded `workspace-write` target
authority with model-shell network disabled. A role-scoped read profile may
configure exactly one loopback AoA MCP (`aoa_evals`, `aoa_stats`, or
`aoa_memo`) from its own required bearer-token environment variable. The
installed CLI consumes that variable in a clean re-exec, removes the bearer
name and value from the runtime's exec-time environment, and carries the exact
bytes in one bounded sealed descriptor. The runtime retains the recovered
credential outside Codex and starts an
attempt-local loopback proxy which injects it only while relaying to the fixed
owner endpoint. The runtime explicitly enables Codex 0.147's
`mcp_2026_07_28` client mode for MCP-bearing roles. The proxy rejects absent,
legacy, duplicate, or otherwise mismatched protocol-version headers and
preserves the admitted exact `2026-07-28` version on the upstream hop; it does
not translate or relabel legacy traffic. Codex receives a random attempt-scoped proxy path with no
bearer environment variable; its model shell has network disabled, its
filesystem profile denies `/proc`, and it cannot use that path directly. The
relay forwards streaming response bytes as they
become available. Before terminal finalization it stops admission, closes all
active client and upstream sockets, and joins its handler threads, so neither
the path nor an already-authenticated connection survives the attempt. Ambient
MCPs and the other role servers remain absent. For both `read-only` and
semantic `workspace-write`, Codex uses the stable child-only descriptor mount
as its execution root and receives `TMPDIR` in the sibling attempt-local
scratch directory. The source checkout is passed to the controller only for
owner-side manifest checks; it is never the actor cwd or writable root. A
workspace-write actor may change only task `allowed_paths` inside the projection;
the `.` sentinel names the workspace root with the same safe-relative-path
semantics in writer execution and reviewer preparation. The controller returns
those changes as the canonical actor delta and leaves the source checkout
unchanged. The invocation receipt records the fixed child
coordinate while result evidence records the controller-owned host projection.
The descriptor is the child binding; the final pathname/device/inode comparison
is the durable closeout binding. The
actor-delta authority check admits an ordinary changed path only when its
safe-relative path is inside `allowed_paths`. A created or deleted directory
that is a strict ancestor of an allowed path is admitted only when the same
exact actor delta also contains an actually changed descendant that passes that
ordinary check; a compact `changed_paths` receipt cannot establish structural
parent authority. Symlinks, type changes, mode changes, siblings, malformed
paths, and empty structural ancestors remain out of scope.
optional `source_evidence_paths` field governs anchored workspace citations and
falls back to `allowed_paths` only for older v1 tasks. Neither field authorizes
commit, push, PR, merge, tag, release, publication, service mutation, secret
access, or global config mutation.

The initial model-organ contours expose exact ABI aliases:
`landing-readonly-v2`, `landing-workspace-write-v2`,
`landing-workspace-write-preview-v1`, and
`structured-owner-duty-workspace-write-v1`. Each retains the same bounded
generic posture for its route: the read alias is `read_only` with `read_only`
effects, the direct write aliases are `workspace_write` with `repo_mutation`
effects, and the preview-capable write alias is `workspace_write` with the
exact `read_only` plus `repo_mutation` effect classes required when one coder
incarnation owns both a preview and mutation step. The task still names
`repo_mutation` as the only mutation route. Both landing write aliases
additionally bind the same model-neutral `landing-validation-v1` environment.
Its pytest distributions,
packaged `aoa_sdk`, and clean tracked `aoa-stats` snapshot are files inside the
verified content-addressed release. Admission preflight is a stable probe
environment and does not receive attempt-local Python cache routing through the
state root. Every real start or resume attempt, including generic structured
owner-duty writers, receives a runtime-generated
`PYTHONPYCACHEPREFIX` beneath its distinct attempt-local scratch directory,
outside the actor projection. The same runtime-owned shell map supplies
`PYTHONNOUSERSITE=1`, bytecode suppression, and pytest cache-provider
suppression without changing the owner-signed validation argv. A resumed
attempt receives a new scratch coordinate and therefore a new prefix. Landing
profiles additionally receive their verified-release `PYTHONPATH` and
`AOA_STATS_ROOT`; the isolated shell `HOME` remains empty. This is a positive
tool grant, not owner authority and not an ambient-path exception.
All aliases remain no-MCP, no-network, and no-external-effect. The alias must
match the realization and incarnation binding exactly; it does not choose the
task family, selected role chain, domain procedure, or model-fit outcome.

Codex runs beneath a Linux supervisor that owns a separate process group but
does not create an outer PID or network namespace. Inference adds only the
rootless user+mount contour described above. Live proof must show that this
still leaves Codex's own `codex-linux-sandbox`/bubblewrap namespace construction intact. The exact Codex
0.147 invocation disables legacy Landlock fallback; for this bounded filesystem
posture that version requires bubblewrap. Model commands therefore run in its
private PID and network namespaces, or the attempt fails rather than exposing
the credential-bearing worker. Before it
launches Codex, the supervisor verifies the exact worker PPID, enables
`PR_SET_CHILD_SUBREAPER`, requests `SIGTERM` through `PR_SET_PDEATHSIG`, and
checks the PPID again to close the parent-death setup race. It then opens the
resolved executable without following symlinks, copies and re-hashes those
exact bytes into a sealed immutable descriptor, and executes
`/proc/self/fd/<fd>` with that descriptor inherited. In-place source mutation
after admission therefore cannot change the bytes that execute.
If identity publication or the final parent check fails, the supervisor retains
its launch-gate endpoint until the blocked wrapper has been killed and reaped.
The wrapper itself retains the peer endpoint, so even an abnormal supervisor
exit cannot turn EOF into permission; only the successful path writes the
release byte.
The version, auth, and model-catalog preflight probes use the same verified-fd
route. Preflight also performs one network-disabled `codex sandbox -P` command
through the outer read-only bind contour, so nested bubblewrap
compatibility is exercised rather than inferred from installed files. Its exact
mount-wrapper and mount-launcher digests are retained and rechecked before
supervisor launch. The three independent Codex metadata probes run
concurrently as distinct start-new-session supervisor process groups; after
their outputs are admitted, the independent subreaper and masked nested-sandbox
probes do the same. Every probe retains its own timeout, verified executable
route, stdout/stderr result, and deterministic failure class. Admission waits
for the complete group, and any incomplete group is terminated and reaped by
exact process-group identity before the error can return. This changes only
latency: no probe, worker repetition, digest check, or fail-closed result is
removed. Inference additionally binds the exact open actor workspace
descriptor and never re-resolves the host pathname in the child. The retained
controller descriptor plus final pathname identity check turns a same-UID
replacement into typed authority-blocked evidence.

Durable v1/v2 states remain readable for status, event, and terminal-result
recovery. They cannot start another attempt without a safe v3-or-newer
runtime-owned projection and baseline; the attempt fails closed instead of
inventing or backfilling historical projection proof. Durable v3 projections
remain resumable after v4 introduces the stable owner-request identity form.

The runtime emits result v2. Every v2 receipt carries the actor projection,
baseline, source-before, and source-after references; completed,
review-required, paused, and interrupted receipts additionally require exact
final actor manifest, actor delta, source-final manifest, and non-null manifest
match observations. Legacy result v1 remains readable but is never emitted by
the current runtime.

On normal exit, controlled termination, or worker death, the supervisor adopts
or enumerates the exact descendant closure in `/proc`, checks PID start ticks,
and applies bounded TERM then KILL cleanup. This includes TERM-resistant
descendants that call `setsid`. An attempt-local interrupt request binds the
signal to the session, attempt, supervisor PID, and process start ticks; only
then may the worker finalize an `interrupted` receipt suitable for exact-thread
resume. Unexpected worker death produces a typed failed result and is not
misrepresented as a controlled checkpoint. If its recovered command history
contains a forbidden, unavailable, or unclassifiable indirect effect, that
death closes as `authority_blocked` instead of erasing the authority breach
behind an ordinary process failure. Failure closeout also evaluates the final
actor delta and source manifest before choosing the wake route: read-only drift,
an out-of-scope writer path, or source drift promotes the result to
`authority_blocked` even when the original process failure was ordinary. It
uses the same exact actor-delta relation as normal finalization, including the
peer-descendant proof for structural parents; if actor projection observation
or coordinate binding fails, its typed
`actor_projection_observation_gap` or `actor_projection_coordinate_drift`
code is preserved rather than replaced by a generic manifest code.

While Codex is live, signal handlers notify a nonblocking self-pipe for child
state and termination events. The supervisor therefore sleeps in `select`
rather than enumerating all of `/proc` at the 50 ms cleanup cadence. A
one-second nonblocking `waitid` reap fallback bounds coalesced or lost `SIGCHLD`
notification without scanning procfs; the tighter polling and full descendant
enumeration are reserved for bounded TERM/KILL cleanup.

This userspace contract does not claim survival of a direct, out-of-contract
`SIGKILL` delivered to the supervisor itself. A kernel-enforced guarantee for
that case requires a separately designed and admitted compatible cgroup
containment route.

## Lifecycle and usage metering

```text
preflight -> prepared -> running
                         |-> completed/review_required/authority_blocked/failed
                         |-> controlled interruption -> interrupted
                                                    -> exact-thread resume
```

The controller counts cumulative input, cached-input and output tokens,
active wall time, turns, output bytes, and executed commands across attempts.
These observations do not become predeclared execution ceilings: the runtime
does not stop an incarnation merely because one of the counters reaches a
chosen number. This preserves agent initiative and leaves comparative cost and
benefit interpretation to `aoa-stats` and `aoa-evals` after measurement.
Host-side resource estimates may support safe launch admission, but remain
observations rather than token, time, turn, output, command, cost, or memory
budgets for the admitted incarnation.

Token values are observations from Codex `turn.completed` events, not inferred
estimates. If a controlled interruption ends an attempt before that event, the
terminal result carries `usage_observation.status=partial` and an exact
attempt/reason/event gap. The recorded numeric values remain the sum of usage
actually observed across attempts; a later resume does not relabel them as a
complete total or invent the unavailable interrupted-attempt usage.

Under `chatgpt_quota`, the runtime records the reported token components but
does not fabricate a USD cost. A provider-enforced context/quota limit,
explicit operator interruption, process death, identity drift, an invalid
protocol record, or invalid JSON/schema remains runtime evidence and produces
a typed result whenever the exact materialized owner inputs remain
trustworthy. The bounded maximum size of one JSONL protocol record is a parser
safety invariant, not a task or research budget.

Finalization rebuilds and durably records the full workspace manifest rather
than comparing only porcelain status. Every tracked path is hashed even when
Git marks it assume-unchanged or skip-worktree, and those index flags are
recorded explicitly. A tracked gitlink fails admission as
`workspace_submodule_unsupported` until the runtime owns a recursive manifest
for every nested submodule worktree byte. An untracked or ignored directory
with its own `.git` administrative marker likewise fails as
`workspace_embedded_repository_unsupported`; a digestless directory entry may
not conceal a separately governed repository. Same-status byte changes, ignored and untracked bytes,
path kind, symlink target, size, binary diff, and HEAD drift therefore remain
observable. A non-following `lstat` inventory cross-checks the complete
filesystem tree instead of trusting Git to enumerate every entry; FIFO,
Unix-domain socket, device, and other unsupported special entries fail closed.
Every workspace symlink must resolve to an existing target inside
the exact checkout; an absent or outward target fails admission as
`workspace_symlink_target_unsupported`. The receipt recorded for each exact
validation command carries the workspace-manifest digest observed at command
completion. Report admission normally requires every such digest to equal the
final manifest. If controller-visible command-sandbox teardown settles between
fixed-command receipts, the runtime may instead admit only the selected exact
validation executions that form the complete terminal command suffix in the
task-declared order and whose last receipt equals the final manifest. A later
model command, an incomplete or reordered suffix, or a final mismatch remains
`model_report_validation_workspace_unbound`. Exact owner-fixed validation argv
remain separately classified from model-selected commands, and finalization
still inventories the complete content and private Git body.

The v1 `git_diff_binary_sha256` is now emitted from a full-object-id diff. During
the compatibility window, an existing v1 admission or durable session may retain
the former abbreviated-object-id digest only when every other manifest field is
unchanged and the current workspace reproduces that exact legacy digest. The
compatibility probe tries only the bounded explicit Git abbreviation widths 4
through 64, so a later `core.abbrev` change cannot invalidate an unchanged
legacy workspace and an arbitrary digest substitution remains a drift failure.
New manifests and private actor projections always use the canonical full-object-
id form; compatibility probes use the same sanitized Git environment as
admission, including repository-filter neutralization.

A manifest read that proves
one regular file changed while its bytes or identity were being inventoried,
or a queued directory disappeared before `scandir`, is retried only within one
short bounded observation window. A stable retry is a new complete manifest,
not acceptance of the partial read; exhaustion and every symlink,
special-entry, coordinate, Git-body, or other projection error still fail
closed immediately. An untracked or ignored secret-shaped path, including
conventional credential-config names such as `.npmrc`, blocks admission before
its content is hashed. Read-only manifest drift, HEAD drift, an out-of-scope
write, or a command event whose command text is unavailable fails closed as
`authority_blocked` evidence. If a failure closeout cannot observe the final
manifest, it becomes `workspace_manifest_observation_gap/authority_blocked`
rather than emitting a false ordinary failure receipt. The command observer recognizes wrapped/scoped
Git and GitHub effects plus publication, service, secret-access, and global
configuration command families. Non-owner-fixed interpreter or script bodies,
`find -exec`, `eval`, `xargs`, and process-launch wrappers such as `nice`,
`nohup`, `setsid`, and `stdbuf` are treated as unclassified indirect effects
and authority-block the terminal result by default; exact fixed validation argv
are separately admitted by their owner identity. A task-local
`indirect_command_policy: sandbox_confined` may admit opaque local execution
only when the exact incarnation binding proves the matching read-only or
workspace-write sandbox, approval `never`, disabled network, and no secret or
external-effect authority. Canonical landing-review preparation selects this
policy explicitly for its newly generated read-only task; it does not inherit
the writer task's effect-class policy. Explicit forbidden families remain
blocking, and unexpected worker death retains the stricter unclassified-effect
closeout.
The sandbox remains the primary effect boundary, and command observation is
retained as auditable counterevidence.
Any command argument that names a secret-shaped path is classified as secret
access regardless of the executable name; this prevents an unenumerated direct
reader or encoder from weakening the runtime-wide secret stop-line.
GNU `env -S`/`--split-string` remains opaque instead of being mistaken for an
executable, value-taking `timeout` signal/kill options are consumed before the
wrapped command is classified, and shell control or redirection punctuation is
tokenized even when attached to an argument. Redirection remains an
unclassified authority signal even when the underlying command family is also
recognized. In addition,
`item.started` command evidence is durable before completion; a controller or
worker loss therefore cannot erase an effect that began without emitting
`item.completed`.
Nested shell bodies are inspected only to a fixed parser-safety depth; any
still-pending or syntactically unparsed body at that boundary is itself an
unclassified authority signal rather than an implicitly safe command. Shell
command substitution, backticks, and process substitution likewise fail closed
instead of being treated as inert command arguments. Build, package, test, and
task runners that may execute manifest-, plugin-, or project-defined commands
are opaque for model-issued commands; only an exact owner-fixed validation argv
receives the fixed-validation exemption. Active shell parameter, ordinary glob,
Bash extglob, brace, and tilde expansion is opaque because the event does not
expose the resulting argv; single-quoted and escaped literal text remains
classifiable. Model-issued commands receive a fixed system-only `PATH`; a
direct command is classifiable only when its basename is explicitly admitted
and resolves beneath a stable system bin root. Unadmitted bare names and
directly executed relative, workspace, home, or temporary programs are opaque.
AWK-family program bodies are also opaque because `system()` can launch an
unobserved command. Exact owner-fixed validation remains separately admitted.
An outer shell path is admitted before its `-c` body receives shell-specific
inspection, so a workspace or temporary executable named `bash`, `sh`, `dash`,
or `zsh` cannot impersonate the system shell. Codex and its child shells receive
an empty runtime-owned non-writable `HOME`; `BASH_ENV` and POSIX `ENV` are bound
to `/dev/null`, ambient user startup files are not inherited, and Git's global
and system configuration plus interactive pager/prompt routes are disabled.
GNU sed programs are opaque unless the actual invocation includes GNU sed's
enforced `--sandbox` mode. Git builtins whose output path may invoke
repository-configured diff, textconv, or fsmonitor helpers are likewise opaque;
accepted abbreviated `cat-file` filter/textconv and `hash-object --path` forms
are matched to the same canonical refusal. `hash-object` is classifiable only
with exact `--no-filters` and no later filter-enabling, path, write, or literal
override. Signature-backed `for-each-ref` fields and `rev-list`/`reflog show`
pretty formats are opaque because they invoke a configured verifier. All
OpenPGP, X.509, and SSH verifier program coordinates are additionally forced
to `/usr/bin/false` in controller and Codex Git configuration. The controller's
own exact Git observations remain outside model-issued command
admission, but run with `GIT_NO_LAZY_FETCH=1` so a missing promisor object
cannot dispatch a repository-configured remote helper before admission.
Jq `env`/`$ENV` access remains opaque and classified as secret access under the
runtime's general environment-observation policy. Jq program/module sources are
opaque, while Git-config coordinates supplied through `--rawfile`,
`--slurpfile`, `--argfile`, or ordinary input-file operands are classified as
secret access. Ordinary inline jq transforms, including `.env` data fields and
literal `"env"` keys, remain classifiable. Codex command events do not carry
their effective working directory, so this runtime does not claim exhaustive
semantic recognition of path aliases. Credential separation is instead
enforced structurally: the CLI re-execs without the bearer, consumes it from a
sealed descriptor, never passes it to Codex, and denies `/proc` in the actor
filesystem profile while retaining one host-PID coordinate system for
supervisor cleanup and continuation receipts.
Ordinary ripgrep source search remains classifiable, but `--pre`,
`--hostname-bin`, and `-z`/`--search-zip` are opaque because they spawn helper
processes whose commands are absent from the Codex event. The runtime also
fixes `RIPGREP_CONFIG_PATH=/dev/null`, preventing an ambient config file from
adding one of those hidden process routes to an otherwise ordinary argv.
Ordinary GNU sort remains classifiable, but `--compress-program` and its
accepted GNU abbreviations are opaque because the selected compressor is an
unobserved child process. `git update-ref` is also opaque because it mutates
persistent repository refs below the manifest-visible worktree.
All model-issued `git config` access is opaque: repository, worktree, global,
or system reads may return credential- or command-bearing values, while writes
may alter later command behavior. Controller-owned Git probes remain isolated
under the separately fixed minimal environment.
Model-issued `git remote` admits only name listing; verbose URL output,
`get-url`, and every remote subcommand are opaque because URLs may embed
credentials and subcommands may mutate or dispatch configured transports.
Mutating `git symbolic-ref` and `git reflog` forms, branch/bisect and tree-object
writers, `hash-object -w`/`--literally`, and `fsck --lost-found` are opaque
because their persistent effects remain below the manifest-excluded `.git`
tree. Read-only symbolic-ref, reflog show/exists/list, explicitly filter-free
hash-object, and fsck inspection remain classifiable. Bash `--rcfile` and `--init-file` are
opaque because startup code runs before an otherwise visible `-c` body.
Shell `source` and `.` bodies remain
opaque because the observed argv does not expose the sourced commands. Git
configuration access, including repository-local and per-worktree reads or writes, and
Git global options that can inject
configuration, redirect repository coordinates, select an exec path, or enable
pagination are likewise opaque, as are unknown/external Git subcommands and
ambient environment assignment. Direct known Git builtins remain classifiable.

After the worker repeats executable/model/tool preflight, it rebuilds the full
workspace manifest and requires exact equality with the admission baseline for
every initial posture before launching Codex. This second byte gate covers
ignored and index-hidden files that HEAD and porcelain checks cannot observe.

Any model evidence reference beginning with `source:` is semantic, not opaque
prose. It must resolve to a regular non-symlink file inside the exact workspace
and the task's `source_evidence_paths`; optional `#Lx-Ly` ranges must exist and
optional symbol anchors must occur in the bounded source bytes. Absent files,
escaping paths, out-of-evidence-scope paths, and false anchors fail the report
before its findings can enter independent review. Stable immutable-input refs
remain `immutable:<input-id>#<anchor>`. A report may additionally cite only the
reserved `runtime:workspace-final-manifest#<anchor>` identity for post-exit
workspace state. The controller creates that manifest before report admission
and validates a line anchor against the exact runtime-owned bytes. A symbolic
anchor must name either one exact top-level JSON member or one exact
`content_entries[].path`; substring matches such as `git_head` inside
`source_git_head`, and partial path matches, are false anchors. Arbitrary
runtime paths or aliases remain inadmissible.

An independent reviewer may also receive one controller-generated
`nested-evidence-namespace` derivative when its immutable packet contains a
complete earlier producer graph. Each entry binds the producer task/result/
report/delta digests, the exact artifact occurrence, and either an exact
upstream actor-envelope digest, a final-manifest source digest plus anchored
excerpt, an exact final-manifest line/member/content-entry value, a delta-bound
output, or a recorded validation observation. Matching
an alias by name is forbidden: the producer's original source digest must lead
to one and only one current envelope. A packet without the complete producer
task/result/report/delta/output envelope stays on the prior model-only route;
it never receives a partial namespace. Once a complete graph is admitted, any
missing, ambiguous, drifted, or out-of-scope nested edge rejects the review
before inference. A model may cite a
closed entry as `runtime:nested-evidence-namespace#<entry-id>`, but must still
judge the semantic claim independently; the derivative neither rewrites prior
artifacts nor creates owner truth. The model prompt contains only a compact
summary bound to both the namespace's canonical digest and the exact artifact
digest. Its `materialized_path` is admitted read-only in the attempt-local
Codex permission profile; the reviewer must select only needed entries rather
than copy the complete namespace into the transcript.

Evidence-reference arrays are non-empty and every occurrence is independently
resolved against its exact source, immutable-input, or runtime-owned bytes.
Because the admitted Structured Outputs subset cannot express `uniqueItems`, an
exact repeated reference is preserved in the raw model report and treated as
idempotent rather than converting an otherwise valid review into a runtime
failure. Repetition never substitutes for a distinct reference or bypasses any
path, identity, or anchor check. Semantic report failures retain their exact
diagnostic message in the controller-owned failure receipt.

A task with `review_required=true` cannot yield `status=completed`; it must
preserve the independent-review gate. Read-only reports must use
`artifact_paths=[]`. A repo-mutation report may name only regular non-symlink
files inside the allowed workspace roots that differ from the immutable
baseline; absent, pre-existing, unchanged, escaping, and symbolic labels fail
closed.

The terminal decision names the direction of the handoff rather than collapsing
writer and reviewer authority. A non-review writer at the mandatory review gate
returns `review_required/submit_for_review`. Only an `independent_review` posture
that confirms a blocker may return `review_required/return_for_repair`. Other
terminal execution failures use `failed/stop`; their residual and re-entry
fields may describe a repair route without changing reviewer authority.
The reviewer task binds that negative outcome to its own
`transition.review_required_status`; the successful `target_status` is not
reused and the model cannot mint an unbound repair transition.

Resume requires the exact session ID, durable Codex thread ID, and current
event cursor. The model may propose a re-entry condition, but the runtime maps
observed status to the binding's event-filtered wake policy; the model cannot
decide whether the parent wakes. Its proposed action must exactly match the
selected bound wake condition.

Every main-session state save binds the normalized event-stream digest and
last sequence. If a process stops after fsync of one or more complete events
but before saving state, the next locked load advances the cursor only when
the previous digest matches an exact prefix and the remaining records are
schema-valid, contiguous, and owned by the same session. Missing, truncated,
rewritten, partial, duplicate-sequence, or foreign streams fail closed. The
normalized payload of every Codex event carries a runtime-reserved semantic
delta. Recovery validates and replays that delta for thread identity, turn and
usage counters, and exact executed-command receipts before saving the advanced
cursor or classifying worker death; a Codex-authored collision with the
reserved field or a non-replayable delta fails closed. The
append-only history is hashed and validated incrementally: only one protocol
record has a parser safety boundary, while the cumulative stream has no
runtime-authored size budget.

If the worker exits after atomically replacing the canonical terminal
`result.json` but before the final state rewrite, worker-death observation first
attempts a locked semantic recovery. Recovery requires the current attempt
count, session/model/task/thread identities, terminal status, complete event
digest, invocation identities, and every evidence digest to remain exact. For
an owner-contour session it also recomputes the stable owner-request reference
from the admitted request bytes and requires the separate path-addressable
snapshot to remain in result evidence. A
prior result deliberately left at the canonical path during resume has a lower
attempt count and is not mistaken for the current terminal commit. Only when no
current recoverable result exists does unexpected worker death produce its own
typed failure receipt.

Every terminal closeout copies the exact `result.json` bytes into its attempt
directory and snapshots every unique artifact named by that result before any
later resume can change a session-wide evidence surface. Before admitting a
resume, the controller rebinds its stable owner-request identity and immutable
snapshot to durable admission state, then validates the current terminal result
and this preserved closure. A schema-validated closure receipt binds each
original coordinate and digest to its immutable snapshot; later event appends
or final-manifest replacement therefore cannot make the prior result
unverifiable. Both the exact result and closure receipt enter the
continuation's event/evidence chain. A
caller may bind `previous_result_digest` on any resume; when supplied it must
match exactly. This prevents a continued result from erasing the checkpoint,
interruption, or review receipt that justified re-entry.

A resume may also carry `evidence_inputs`. Each entry supplies a stable input
ID, exact UTF-8 content, and full provenance whose artifact digest must match
those bytes before inference. The controller does not follow a caller-supplied
host path. It retains the original bytes below `controller-immutable`, emits a
source-coordinate-sanitized actor envelope below `immutable`, expands only the
session-local report schema with that stable `immutable:<input-id>` identity,
and records the materialization in the append-only event stream. All entries
are validated and assigned unoccupied coordinates before any bytes are
written; a duplicate, conflicting identity, digest mismatch, or occupied
coordinate fails closed without starting a new attempt. Existing task,
continuation, role, model, workspace, effect, and external authority remain
unchanged. The previous terminal result and evidence closure remain immutable.

A failed session is not generally resumable. Three explicit same-thread
recovery routes exist; none retries automatically. A `review_followup` may
continue a read-only `independent_review` incarnation rejected only as
`model_report_identity_mismatch` or `model_report_transition_mismatch`, with no
changed paths and an exact matching final workspace manifest. A
`bounded_repair` may continue a
`bounded_execution`/`repo_mutation` incarnation rejected by model-report
admission only when the owner source still matches, actor final-manifest and
delta evidence are present, and every exact actor-delta entry passes the same
original task's `allowed_paths` relation. Structural parent entries therefore
require their exact allowed descendant peer; recovery never infers directory
authority from compact `changed_paths`. This writer route preserves the same
role, thread, projection, and authority envelope; it does not convert the actor
to read-only or grant a new path, effect, source, or external authority.

A `capacity_recovery` may continue the exact role after Codex reports the
current ChatGPT usage-limit protocol pair before its first completed turn. The
runtime admits this route only when the per-attempt raw JSONL artifact is
digest-bound by the prior result and ends with an exact top-level provider
`error` plus identical `turn.failed` message. The prior result must additionally
prove zero turns, zero observed tokens, no commands, no changed paths, matching
source and actor manifests, and complete actor final-manifest/delta evidence.
The current typed failure is `provider_capacity_unavailable`; a historical
`codex_process_failed` result may use the same route only when those exact raw
events independently prove the legacy classification. Stderr, model-authored
text, substring matching, an arbitrary process failure, or a drifted evidence
artifact cannot activate the route.

All failed-session recovery requests must bind the prior `result.json` digest,
session, thread, and event cursor. Before continuing the same Codex thread, the general resume
preservation rule verifies and retains that failed result and its evidence
closure. A route-specific admission event records the digest. Authority,
source-manifest, projection-closure, or out-of-scope-change failure does not
enter failed-writer report recovery; an actor in an ordinarily resumable
`authority_blocked` state remains governed by that separate continuation
contract.

## Independent review and A2A return

Canonical review preparation starts no model process. It accepts one terminal
`completed` or `review_required` read-only or bounded repo-mutation writer only
when the runtime failure code is null and all launch, task, report,
immutable-input, and runtime-owned final-workspace-manifest bytes retain their
admitted digests. Every writer immutable input keeps its stable ID;
`writer-runtime-result`, `writer-model-report`, and a distinct
`review-workspace-manifest` are added as evidence. A mutation writer requires
an explicitly supplied plan-bound reviewer role contract and a read-only
realization with the same provider, runtime, model, and effort. The resulting
reviewer has a different task, incarnation, and session, uses read-only tools
and permissions, preserves the writer's `source_evidence_paths` and observe-only
metering, and has no workspace-write or external-effect authority.
The writer may be a historical `transport_study_fixture` or an evidence-complete
`owner_contour`. The prepared reviewer remains `transport_study_fixture`; A2A
export accepts only the historical fixture pair or the exact
`owner_contour`-writer/prepared-reviewer pair. The latter does not downgrade the
writer: its owner request, SDK v4 transport preference, binding v2, durable
state, report, and terminal actor evidence remain required and digest-bound.
Before reviewer preparation consumes a terminal writer result, the writer
runtime revalidates its canonical result under the durable session route and
rebinds both the stable owner-request identity and path-addressable admitted
snapshot. Review-seed issuance repeats the same check under the writer lock.

A reviewer formed independently by the role-first `aoa-agents` route instead
enters as `owner_contour`. The generic owner-contour exporter requires the exact
writer task, result, report, and all report-named output digests to be immutable
reviewer inputs; requires a different incarnation and Codex thread, the same
domain owner, the writer task as reviewer parent, and the exact reviewed result
path; and requires the reviewer to be `independent_review`, read-only,
external-effect-free, and zero-delta. Both SDK v4 summon request/schema pairs
are revalidated while both session locks are held through atomic publication.
This stronger pair records `owner_contour_immutable_evidence`; it does not
convert runtime completion into owner acceptance, model fit, eval proof, or
publication authority. Historical fixture and mixed compatibility pairs keep
their existing admission path.

An evidence-complete `owner_contour` writer may predate the reviewer input ABI
without losing its role continuum. If its task lacks the selected workspace
manifest input, review preparation may create
`writer-source-baseline-manifest` only from the canonical
`source-manifest-before.json` whose path and digest match result and state,
whose value equals the durable `workspace_manifest_baseline`, and whose
workspace and HEAD match the launch. If its task lacks
`summon-request-schema`, preparation may create
`writer-summon-request-schema` only from the exact selected SDK v4 bytes and
only when the writer request already names that schema identity and version.
Both are controller-derived reviewer inputs with new provenance; neither is
reported as an original writer input. The reviewer also receives a distinct
active `summon-request-schema` for its own request. A2A export admits the
compatibility schema only when the derived writer copy and active reviewer SDK
copy remain byte-identical and provenance-bound during the final locked
revalidation. This exception does not apply to transport fixtures and does not
widen task, role, model, permission, effect, or owner scope.

The same early owner-contour compatibility window admits a mixed summon
binding in which the exact request is the sole typed `summon_request` artifact
while its SDK v4 decision remains a generic scenario input. The decision must
also be the exact controller-owned writer task input and appear unchanged in
the plan snapshot and incarnation continuation. Missing, duplicated, foreign,
or transport-fixture mixed bindings remain rejected.

The reviewer receives its own canonical SDK v4 summon request and decision;
the writer request remains immutable review evidence. The derived reviewer plan
and launch bind the current admitted runtime profile required by the new
incarnation; they never reuse an older writer profile as active authority. The
historical writer launch, result, and plan remain immutable review evidence.
The preparer resolves the selected reviewer specialization's exact
owner-authored `aoa-agents` capability pack, adds it without removing unrelated
scenario capabilities, assigns it to every reviewer-bound active step, and
names the same capability ID in the reviewer SDK request. When the writer is
already the reviewer role, preparation retains only the unique capability
named by the canonical writer request and present in its admitted scenario;
missing or multiple matches are not inferred. Every writer and
reviewer summon request must carry a non-empty capability set contained by its
admitted plan. Before inference, the request must also match the exact role,
incarnation, parent task, session, named outputs, transport, review posture,
and workspace of the admitted task and launch. Both the semantic and
capability bindings are rechecked during A2A export.
The derived reviewer plan
reassigns only the active writer
task/request step from the writer role to the exact plan-bound reviewer role as
`read_only`. Existing reviewer-bound steps are normalized to the same read-only
effect posture required by the incarnation; non-reviewer DAG roles and steps
remain unchanged. A2A export verifies the materialized request/schema bytes,
typed plan binding, role/incarnation/task semantics, requested outputs, and the
caller-supplied writer request digest before it can emit a child result.
Symbolic named outputs come from the already admitted runtime task and remain
separate from model-authored workspace artifact paths; the exporter returns
both and requires the writer and reviewer summon requests to be satisfied.
The exporter also serializes the initially loaded reviewer result to its exact
artifact digest and requires the later locked durable state to retain that
same digest. Immediately before output publication, it reacquires the reviewer
session lock while retaining the writer lock, revalidates the canonical result,
review seed, both summon requests and schemas, and every exported writer and
reviewer report/event/workspace/actor-final/actor-delta artifact plus the
canonical writer runtime result itself, constructs the
payload from that locked snapshot, and holds both locks through the atomic
output write. The published child payload self-identifies as
`abyss_stack_external_codex_a2a_return_v1`; downstream closeout never has to
infer the runtime-owned schema from a filename or caller assertion. Result,
task, durable state, and final locked state must all retain
task family `landing_review`. A reviewer
continuation racing the export therefore either precedes a failed revalidation
or follows a durable export; it cannot mix a stale verdict with newer bytes.

The reviewer task does not require a third review by default. It may return
`completed/proceed` when no blocker remains or
`review_required/return_for_repair` when one is confirmed; both routes stop
without waking the parent unless unresolved owner authority is observed.

An export requires:

- writer and reviewer terminal runtime results, with the reviewer accepted only
  as `completed` or `review_required` and with no runtime failure code;
- different incarnation IDs and different Codex thread IDs;
- reviewer task family `landing_review`;
- reviewer immutable inputs bound to the exact writer `result.json`, model
  report, source manifest, actor final manifest, and actor delta digests;
- one controller-issued review-seed envelope, recomputed under the writer lock
  and bound to the writer session, incarnation, thread, result, final actor
  manifest, actor delta, source manifest, reviewer launch, and durable reviewer
  state;
- exact writer and reviewer actor-final-manifest artifact digests, identical
  content/private-Git state, and a zero reviewer delta;
- reviewer parent task ID equal to the writer task ID;
- exact writer and reviewer SDK v4 summon request/schema bindings, with every
  requested output present in the child result;
- the same target owner and a terminal review decision.

A failed reviewer runtime is preserved as review counterevidence but cannot be
exported as a reviewed A2A result. If the narrowly admitted identity/transition
follow-up above later produces an accepted terminal review, export uses that
final result while its evidence chain retains the exact failed result. The
accepted reviewer `report_ref` itself must contain the terminal review
decision.

## Parent yield and filtered re-entry

Parent re-entry is a separate runtime lifecycle, not ordinary child-session
resume. `yield-parent` validates and privately materializes the exact parent
obligation, child task, incarnation binding, role, model realization, and SDK
schema bytes. Before inference it persists a v2 `yielding` state with the exact
obligation and an empty event stream. Each retry uses a new numbered yield
attempt directory and preserves all incomplete predecessor bytes; a still-live
prior supervisor blocks overlap. A durable complete `inference_yielded` event
carries the exact turn delta, so append-before-state-save recovery advances to
`yielded` and registers the wait without a second Sol turn. It starts a distinct `gpt-5.6-sol` max process with built-in
multi-agent behavior disabled and requires one structured yield report. After
`turn.completed`, that process exits; the controller persists the parent Codex
thread and a `waiting` state. No model inference or model-driven polling remains
alive while the child works.

`reenter-parent` initially admits only the exact terminal child result named by the
obligation and binding. The supplied absolute `result.json` must occupy the
canonical `sessions/<hash(session_id)>/` directory and match the sibling
durable `state.json` result path/digest, terminal identity/status/thread, and
canonical event path/terminal sequence. While holding the canonical child
session lock it also rebinds the stable owner-request identity and immutable
request snapshot to the child's durable admission state. It then revalidates the child's task,
incarnation, result schema, event-stream digest, evidence inclusion,
continuation, return owner, deferred decisions, and status-selected SDK wake
condition while holding the canonical child session lock through the durable
parent `child_event_admitted` append. Before that append, the runtime selects
the matching immutable `attempts/<number>/runtime-result*.json` snapshot,
verifies its complete evidence closure, and binds that snapshot—not the mutable
canonical `result.json`—as the admitted parent input. For a waking event it also
materializes and digest-binds the parent-local distilled return before the
admission event. Exactly one
`external_agent.wake_evaluated` event must match the runtime result. Failed,
missing, false, duplicate, or non-parent events are preserved and filtered
without a second Sol turn.

The re-entry event stream and state digest form a recoverable pair. If the
controller stops after fsync of a complete event but before the state rewrite,
the next load may advance `events_ref` only when the current JSONL bytes are a
strict extension of the previously recorded digest and every event remains a
contiguous record for the same re-entry identity. Public status reads acquire
the same re-entry lock as state transitions, so recovery cannot overwrite a
newer concurrent state. Rewrites, truncation,
partial records, and foreign identities remain fail-closed drift.
Recognized appended events also replay their semantic state delta: the complete
yield turn and registered wait, admitted child receipt and wake evaluation,
filtered or failed status, or the exact completed parent turn and result reference. Event recovery therefore
cannot leave a successful re-entry stranded as `reentering`.

The admitted child event, wake evaluation, immutable attempt snapshot, and
distilled return are saved before the state becomes `reentering`. A replacement
controller recovering either `waiting` after the admission append or
`reentering` after the start append reloads only those already admitted bytes;
it does not consult the live canonical child result again. Re-entry turns use
numbered, process-contained attempt directories: a live prior supervisor
blocks overlap, an incomplete dead attempt is preserved before retry, and a
digest-bound completed-turn receipt is reloaded without a second inference.
The child admission and `reentry_started` events are never appended twice.

When and only when the admitted event selects `wake_parent`, the controller
builds a compact return bound to the child-result and observed-event digests,
then invokes `codex exec resume <exact-parent-thread-id>`. The resumed Sol must
return a typed parent-reentry report whose identities and authority action
match that return. Both the initial yield and resumed parent turn are launched
with an isolated non-writable `HOME` and all available tool-bearing features
disabled before inference; their event admission still accepts only passive
reasoning or agent-message items. Any command execution, MCP call, file change,
or other tool item fails closed as a second boundary instead of broadening its
authority. A successful cycle therefore has two completed turns on one
parent thread with an inference-free durable wait between them. Re-entry
validation failure is terminal evidence; only a contained controller/process
interruption without a terminal re-entry verdict is recoverable or retryable.

This use of the current Codex exact-thread resume surface proves the product
transport needed by L2; it does not make Codex the owner of wait significance,
role truth, model fit, proof, acceptance, or effects. Those remain with the
binding/runtime and their named owner surfaces.

The export is only a `child_task_result` candidate for the existing
`agent-os-adapter` A2A return-review lane. That downstream lane still requires
the exact summon request and decision chain. Neither export nor downstream
review is an eval verdict, owner acceptance, landing, or proof of benefit.
