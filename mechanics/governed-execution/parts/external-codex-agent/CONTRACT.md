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
before the first dynamic executable, derives an adjacent non-executable
read-only companion through `/proc/self/exe`, and executes fixed
`/usr/bin/python3 -I -B`. Installation, activation, and status compile and
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
    ready task-local DAG, accepted responsibility transfer, domain procedure
    refs, child scope, external-process/session posture, and observe-only usage
    semantics must match the launch and continuation exactly. Owner semantic
    self-digests and immutable transport-byte digests remain distinct and both
    are verified.

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
persisted in runtime state and revalidated before every inference; drift fails
closed. This prevents a known runtime identity or forwarded immutable input
from being mistyped or plausibly aliased in an otherwise substantive report
without weakening the post-output semantic identity and byte checks.

## Process and tool boundary

The argv uses `codex exec`/`codex exec resume`, structured JSONL, a strict final
schema, explicit model and effort, `approval_policy=never`, an explicit cwd and
sandbox, `--ignore-user-config`, `--ignore-rules`, `--strict-config`, and
`--disable multi_agent`. The child inherits only an allowlisted non-secret
environment; secret-shaped variable names are excluded again from the Codex
shell environment. No TUI or built-in `spawn_agent` surface participates.

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
worker retains that upstream credential outside Codex and starts an
attempt-local loopback proxy which injects it only while relaying to the fixed
owner endpoint. Codex receives a random attempt-scoped proxy path with no
bearer environment variable; its model shell has network disabled and cannot
use that path directly. The relay forwards streaming response bytes as they
become available. Before terminal finalization it stops admission, closes all
active client and upstream sockets, and joins its handler threads, so neither
the path nor an already-authenticated connection survives the attempt. Ambient
MCPs and the other role servers remain absent. For both `read-only` and
semantic `workspace-write`, Codex uses the stable child-only descriptor mount
as its execution root and receives `TMPDIR` in the sibling attempt-local
scratch directory. The source checkout is passed to the controller only for
owner-side manifest checks; it is never the actor cwd or writable root. A
workspace-write actor may change only task `allowed_paths` inside the projection;
the controller returns those changes as the canonical actor delta and leaves the
source checkout unchanged. The invocation receipt records the fixed child
coordinate while result evidence records the controller-owned host projection.
The descriptor is the child binding; the final pathname/device/inode comparison
is the durable closeout binding. The
optional `source_evidence_paths` field governs anchored workspace citations and
falls back to `allowed_paths` only for older v1 tasks. Neither field authorizes
commit, push, PR, merge, tag, release, publication, service mutation, secret
access, or global config mutation.

The write contour exposes two exact model-organ ABI aliases:
`landing-workspace-write-v2` and
`structured-owner-duty-workspace-write-v1`. Each retains the same bounded
`workspace_write`, `repo_mutation`, no-MCP, no-network, no-external-effect
posture. The alias must match the realization and incarnation binding exactly;
it does not choose the task family, selected role chain, domain procedure, or
model-fit outcome.

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
resolved executable without following symlinks, re-hashes that exact file
descriptor against the admitted digest, checks that the inode did not change
during hashing, and executes `/proc/self/fd/<fd>` with the descriptor inherited.
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
supervisor launch. Inference additionally binds the exact open actor workspace
descriptor and never re-resolves the host pathname in the child. The retained
controller descriptor plus final pathname identity check turns a same-UID
replacement into typed authority-blocked evidence.

Durable v1/v2 states remain readable for status, event, and terminal-result
recovery. They cannot start another attempt without a safe v3 runtime-owned
projection and baseline; the attempt fails closed instead of inventing or
backfilling historical projection proof.

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
`authority_blocked` even when the original process failure was ordinary.

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
`workspace_symlink_target_unsupported`. The receipt recorded for each exact validation command carries the
workspace-manifest digest observed at command completion; report admission
requires the final manifest to retain that digest. An untracked or ignored secret-shaped path blocks admission before
its content is hashed. Read-only manifest drift, HEAD drift, an out-of-scope
write, or a command event whose command text is unavailable fails closed as
`authority_blocked` evidence. If a failure closeout cannot observe the final
manifest, it becomes `workspace_manifest_observation_gap/authority_blocked`
rather than emitting a false ordinary failure receipt. The command observer recognizes wrapped/scoped
Git and GitHub effects plus publication, service, secret-access, and global
configuration command families. Non-owner-fixed interpreter or script bodies,
`find -exec`, `eval`, `xargs`, and process-launch wrappers such as `nice`,
`nohup`, `setsid`, and `stdbuf` are treated as unclassified indirect effects
and authority-block the terminal result; exact fixed validation argv are
separately admitted by their owner identity. The sandbox remains the primary effect
boundary, and command observation is retained as auditable counterevidence.
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
literal `"env"` keys, remain classifiable. Codex command
events do not carry their effective working directory, so this runtime does not
claim exhaustive semantic recognition of procfs path aliases. Credential
separation is instead enforced structurally by removing the upstream bearer
from Codex and hiding the credential-bearing worker behind Codex's private PID
namespace.
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
and validates the anchor against the exact runtime-owned bytes; arbitrary
runtime paths or aliases remain inadmissible.

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
digest, invocation identities, and every evidence digest to remain exact. A
prior result deliberately left at the canonical path during resume has a lower
attempt count and is not mistaken for the current terminal commit. Only when no
current recoverable result exists does unexpected worker death produce its own
typed failure receipt.

Every terminal closeout copies the exact `result.json` bytes into its attempt
directory and snapshots every unique artifact named by that result before any
later resume can change a session-wide evidence surface. Before admitting a
resume, the controller validates the current terminal result and this preserved
closure. A schema-validated closure receipt binds each
original coordinate and digest to its immutable snapshot; later event appends
or final-manifest replacement therefore cannot make the prior result
unverifiable. Both the exact result and closure receipt enter the
continuation's event/evidence chain. A
caller may bind `previous_result_digest` on any resume; when supplied it must
match exactly. This prevents a continued result from erasing the checkpoint,
interruption, or review receipt that justified re-entry.

A failed session is not generally resumable. The sole initial exception is an
explicit `review_followup` for a read-only `independent_review` incarnation rejected only as
`model_report_identity_mismatch`, with no changed paths and an exact matching
final workspace manifest. The request must also bind the prior `result.json`
digest, session, thread, and event cursor. Before continuing the same Codex
thread, the general resume preservation rule retains that failed result and a
review-specific admission event records its digest. There is no automatic retry,
and mutation, authority, source-evidence, or other report failures do not enter
this route.

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

The reviewer receives its own canonical SDK v4 summon request and decision;
the writer request remains immutable review evidence. A2A export verifies the
materialized request/schema bytes, typed plan binding, role/incarnation/task
semantics, requested outputs, and the caller-supplied writer request digest
before it can emit a child result.
The exporter also serializes the initially loaded reviewer result to its exact
artifact digest and requires the later locked durable state to retain that
same digest. Immediately before output publication, it reacquires the reviewer
session lock while retaining the writer lock, revalidates the canonical result,
review seed, both summon requests and schemas, and every exported writer and
reviewer report/event/workspace/actor-final/actor-delta artifact, constructs the
payload from that locked snapshot, and holds both locks through the atomic
output write. Result, task, durable state, and final locked state must all retain
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
exported as a reviewed A2A result. If the narrowly admitted identity-only
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
canonical event path/terminal sequence. It then revalidates the child's task,
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
match that return. Both the initial yield and resumed parent turn admit only
passive reasoning or agent-message items; any command execution, MCP call, file
change, or other tool item fails the parent turn instead of broadening its
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
