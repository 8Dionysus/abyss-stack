# External Codex Agent

This part is the `abyss-stack` runtime owner for one explicitly bound Codex
incarnation running as a separate operating-system process. It is not Codex's
built-in subagent transport, a TUI-injection layer, a model router, or an
authority for role meaning, model fit, eval verdicts, owner acceptance, or
landing effects.

The production-shaped admission is role-first and task-family neutral. A goal
first produces an independently owned obligation and `aoa-agents` mandate;
only then may `aoa-models` supply a current realization and `aoa-sdk` bind its
tools, effects, continuation, wake policy, and execution posture. Eval, stats,
memo, and landing are initial useful obligations, not runtime-owned families.
Today an exact `gpt-5.6-luna` max/xhigh realization may satisfy some of those
roles, but no stable command or profile is named after Luna.

The controller:

- verifies the exact `RunPlan`, incarnation binding, task, role, model
  realization, runtime/tool profile, result schema, workspace HEAD, immutable
  inputs, Codex binary digest/version, ChatGPT login, and live model catalog;
- requires every task to preserve the complete runtime-wide forbidden-effect
  set, while terminal classification independently applies that set instead of
  trusting a caller-supplied subset;
- keeps the SDK `summon-request-v4` as the typed active
  `AgentIncarnationBinding.task_request_ref`, while binding the richer
  runtime-owner task separately as an exact snapshot/continuation-pinned
  runtime constraint;
- launches `codex exec --json` in a distinct process with user config and exec
  rules ignored, `multi_agent` disabled, explicit sandbox/approval/cwd/model
  settings, no inherited MCP servers, only the exact role-profile MCP when one
  is required, no model-shell network in the admitted tool profiles,
  and a structured final-output schema whose session-local derivative fixes the
  exact task and incarnation identities before inference;
- persists normalized events, exact thread identity, attempts, PIDs/start
  ticks, argv, usage, active wall time, output bytes, workspace changes,
  the exact final workspace manifest, wake evaluation, and a typed terminal
  result beneath an explicit state root; each state save binds the normalized
  event-stream digest, and a complete append that precedes a crash is recovered
  only as a strict, contiguous extension of that digest; runtime-authored
  Codex deltas replay thread, usage, turn, and command state from such an
  extension before any worker-death closeout; event history is
  verified incrementally with a per-record parser boundary rather than a
  cumulative task budget, and an atomically written terminal result can repair
  the final semantic state save only when its attempt, identity, event, and
  evidence receipts remain exact;
- exposes asynchronous `start` for durable owner-managed sessions and
  `run-to-terminal` for transient cgroup launchers that must keep their main
  process alive until the exact semantic terminal receipt, without adding a
  time, token, turn, output, command, cost, or memory budget; an admitted
  `prepared` session with no attempt or worker is retryable through the same
  exact `start`, and the child cannot pass its one-byte launch gate before its
  worker identity is durable;
- rebuilds the exact byte-level workspace manifest for every tracked,
  untracked, and ignored path at finalization, records assume-unchanged and
  skip-worktree index flags, rejects tracked submodule worktrees until a
  recursive nested-byte contract exists, and rejects untracked or ignored
  embedded Git repositories rather than representing them as digestless
  directories; rejects any workspace symlink whose target is absent or outside
  the exact checkout; drains a
  terminal process stream before finalization, counts tokens/turns/time/output
  without imposing execution budgets, includes ignored workspace bytes without
  reading secret-shaped ignored inputs, holds an inode-scoped exclusive lock
  on the exact runtime-owned actor projection through each active worker attempt
  so separate attempts cannot overlap one projection, and runs Codex beneath a Linux
  parent-death/subreaper supervisor that
  adopts and cleans detached descendants without placing an outer PID or
  network namespace in front of Codex's own sandbox, while retaining exact PGID/SID TERM/KILL
  observation; every Codex preflight probe and inference launch goes through a
  supervisor which opens and re-hashes the executable immediately before exec
  and executes that verified open inode through procfs, so a pathname
  replacement cannot substitute different Codex bytes; inference additionally
  uses a filesystem-only bubblewrap parent (rootless user+mount namespaces,
  but no PID/network namespace) whose launcher and future Codex child are
  separately recorded before a launch gate is released; the exact worker PPID
  and pending termination state are checked again immediately before release;
  a self-peered Unix-socket gate retained through bubblewrap `--sync-fd` makes
  supervisor EOF non-releasing, while an abort kills and reaps the blocked
  wrapper before closing the still-unreleased supervisor endpoint;
  preflight executes the same historical outer mask plus Codex's own inner
  named bubblewrap/private-PID sandbox instead of merely checking their
  binaries, and records the exact mount-wrapper and mount-launcher digests for
  defense-in-depth drift checks;
- materializes every admitted Git baseline into a fresh runtime-owned actor
  projection before inference, rejecting unsupported special entries or unsafe
  symlinks and constructing a private source-independent `.git` body whose
  status/diff exactly match the admitted manifest; the source manifest is
  recorded before and after materialization and must remain identical before
  inference. Staging and publication are relative to one pinned parent
  descriptor, the baseline is inventoried from the still-open staging inode,
  and the public coordinate must name that same device/inode before it can
  become durable state. Publication is non-replacing and rename commitment is
  recorded before verification, so a post-rename failure cleans only the exact
  staged inode through the pinned parent descriptor; a replaced coordinate is retained as typed
  contamination rather than trusted or destructively cleaned. The actor
  baseline/final manifests and canonical delta are durable session artifacts.
  The model receives only the projection as target,
  cwd, and validation root; the source checkout remains the owner acceptance
  surface and is never an actor write target. Reviewer launches may seed an
  exact writer projection only through a controller-issued review-seed envelope;
  reviewer preparation and execution remain valid after the historical source
  checkout disappears;
- opens the actor projection once, inventories that descriptor, and passes the
  same open inode through the supervisor and mount launcher to bubblewrap at
  `/tmp/aoa-external-actor-workspace`. Final inventory uses the retained
  descriptor and closeout rejects any pathname/inode replacement. Codex also
  receives an explicit minimal allowlist permission profile, sanitized
  actor-local Git config, disabled model-shell network, and an attempt-local
  scratch directory;
- keeps controller-original immutable inputs outside the actor permission
  contour and gives the actor only schema-validated derivative envelopes.
  JSON is parsed before source-coordinate removal; arbitrary text is checked
  through bounded nested JSON-escape decoding, including mixed literal/escaped
  text, slash escapes, hex-case variants, and surrogate pairs. Mapping keys and
  values are both sanitized, excessive escape depth and collisions fail closed,
  serialized aliases and invalid-UTF-8 binary shadows are checked through the
  same decoder before any reversible base64 materialization, and
  source aliases are removed from model-facing control views. Workspace
  identity/ancestor coordinates are omitted. A source beneath Codex's built-in minimal-read system roots is
  rejected instead of relying on an allowlist that would expose it;
- resumes only the exact durable thread and event cursor, with explicit
  digest-bound follow-up routes for an unchanged read-only review rejected only
  by an identity-field mismatch and for an authority-safe bounded writer
  rejected only during model-report admission. Writer report repair requires
  unchanged owner source, complete actor manifest/delta evidence, and every
  observed change inside the original allowed paths; it retains the original
  role and authority envelope. Every route preserves each prior terminal result plus
  a digest-bound snapshot closure for all referenced evidence in its attempt
  directory before any admitted continuation;
- emits result v2 with mandatory actor/source provenance for successful returns,
  while continuing to read legacy result v1 and durable state v1/v2 for status and
  terminal-result recovery, while refusing a new inference attempt unless a
  safe v3 runtime-owned projection and its baseline are available;
- turns read-only drift, out-of-scope paths, forbidden effects, identity drift,
  or report-contract drift into typed failure or authority-blocked evidence;
  non-owner-fixed interpreter, script, process-launch wrapper, `find -exec`,
  `eval`, and `xargs`
  commands whose indirect effects cannot be classified are retained as
  counterevidence and authority-block the result by default. A task may instead
  admit `sandbox_confined` local indirection only when the exact incarnation
  binding proves a matching read-only or workspace-write sandbox, approval
  `never`, disabled network, and no secret or external-effect authority;
  canonical landing-review preparation binds that policy into its newly
  generated read-only task rather than inheriting the writer task's policy;
  explicit forbidden command families and abnormal failure closeout still
  fail closed. Shell separators remain
  visible even when attached to arguments, redirection remains an opaque
  authority signal, `env --split-string` cannot smuggle an executable past the
  observer, value-taking `timeout` options cannot hide the wrapped command,
  shell nesting that exceeds the bounded inspection depth fails opaque,
  command/backtick/process substitutions remain opaque executable indirection,
  active parameter, glob (including Bash extglob), brace, and tilde expansion
  plus literal command newlines remain opaque while quoted or escaped literals
  stay classifiable,
  jq environment builtins and externally supplied jq programs/modules are
  opaque and classified as secret access; jq file-loading and ordinary input
  operands that name repository Git config are likewise refused, while ordinary
  inline jq data transforms remain admitted,
  sourced shell bodies through `source` or `.` remain opaque, and Bash
  `--rcfile`/`--init-file` startup code is opaque even before an otherwise
  classifiable `-c` body,
  model-issued commands run with a fixed system-only `PATH`, and only an
  explicit small set of system-resolved executables is directly classifiable;
  unadmitted bare names, directly selected relative/workspace/home/temporary
  paths, and opaque AWK program bodies remain authority-blocking outside exact
  owner-fixed validation,
  outer shell executables pass that same path admission before an inline body
  is inspected; the worker uses an empty, runtime-owned, non-writable `HOME`
  plus inert shell startup variables instead of ambient user profiles, and
  binds `core.hooksPath` through command-scope Git configuration to a separate
  empty, runtime-owned, non-writable directory so repository hooks cannot add
  unobserved execution; model-issued attempts to override that binding remain
  opaque,
  GNU sed is classifiable only with enforced `--sandbox`, and Git builtins that
  can invoke repository-configured diff, textconv, or fsmonitor helpers remain
  opaque; checkout/checkin builtins that can invoke repository-defined content
  filters remain opaque as well, while controller-owned manifest Git probes run
  in a minimal environment with hooks/fsmonitor disabled and diff/textconv
  programs explicitly prohibited; promisor lazy fetching is disabled so a
  missing object cannot dispatch a repository-configured remote helper;
  abbreviated `cat-file` filter/textconv and
  `hash-object --path` forms are covered by the same refusal; `hash-object`
  reads are admitted only with exact `--no-filters` and no filter-enabling,
  path, write, or literal override, while signature-backed `for-each-ref`,
  `rev-list`, and `reflog show` formats are opaque because they invoke the
  configured verifier; OpenPGP, X.509, and SSH verifier programs are fixed to
  `/usr/bin/false`,
  ripgrep remains available for ordinary source search, while `--pre`,
  `--hostname-bin`, and `-z`/`--search-zip` are opaque because they launch
  unobserved helpers; `RIPGREP_CONFIG_PATH` is fixed to `/dev/null` so ambient
  configuration cannot re-enable those modes,
  GNU sort remains available for ordinary ordering, while
  `--compress-program` and its accepted GNU abbreviations are opaque because
  they launch an unobserved helper,
  build/package/test/task runners remain opaque unless they are an exact
  owner-fixed validation,
  all model-issued Git config access, including jq file-loading forms, plus
  alias/external-subcommand dispatch
  and ambient environment assignment fail closed because config reads may
  expose credential- or command-bearing values; `git remote` retains only
  read-only name listing, while URL output and every mutating or
  transport-dispatching form are opaque; `git update-ref` is opaque because it
  mutates repository state below
  the manifest-visible worktree; generic mutators also parse attached
  destination options before admitting `.git` writes; mutating `symbolic-ref`
  and `reflog` forms,
  ref/temporary-object helpers whose effects stay below `.git`, and explicit
  hidden-object write options are also opaque while explicitly filter-free
  read-only hashing remains admitted; Git help forms are opaque as well because configured
  man viewers can dispatch programs,
  any command carrying a secret-shaped path is classified as secret access,
  and commands are durably observed
  from `item.started` rather than only after completion, while exact task validation
  argv remain admitted by their owner-supplied identity;
- cross-checks Git with a non-following filesystem inventory, so a FIFO,
  Unix-domain socket, device, or other Git-invisible special entry cannot evade
  baseline or final workspace observation;
- rebuilds that full manifest after worker preflight and before inference for
  every workspace posture, so ignored or index-hidden drift cannot enter a
  clean-required launch through the preflight window;
- constrains every `immutable:` evidence reference in the session-local output
  schema to the exact materialized input identities, so a plausible alias is
  rejected during structured decoding as well as by post-output byte checks;
- validates every evidence occurrence while preserving exact repeated refs as
  idempotent raw model output, and records the precise semantic failure message
  when report admission still fails;
- keeps mutation/artifact `allowed_paths` distinct from
  `source_evidence_paths`, with a backward-compatible fallback for older task
  packets, and binds claims about post-exit workspace state through the single
  controller-owned `runtime:workspace-final-manifest#...` evidence identity;
- binds every validation claim to an exact observed argv/exit state and the
  workspace-manifest digest observed when that command completed. Every
  receipt normally matches the final manifest; when transient command-sandbox
  teardown settles between receipts, only the complete exact validation suite
  as the terminal command suffix is accepted, and its last receipt must match
  the final manifest. Any later command or final drift still fails. The runtime keeps full
  fail-closed projection inventory while retrying only a bounded regular-file
  read/identity or disappearing-directory enumeration race; a retry rebuilds
  the entire manifest, and
  unsupported entries, coordinate drift, Git-body drift, or repeated change
  still terminate observation; preserves `review_required` as a real gate,
  distinguishes a non-review writer's
  `submit_for_review` handoff from a reviewer's `return_for_repair` verdict,
  binds each negative review to a separate task-owned outcome status,
  binds model re-entry to the status-selected wake condition, admits only
  genuinely produced workspace artifacts, and admits `owner_contour` only with
  a separate exact `aoa-agents` execution request, ready task-local DAG,
  accepted responsibility transfer, domain procedure refs, and pinned owner
  schemas;
- exports an A2A-compatible child result only after a different incarnation
  and different Codex thread reviewed the exact writer runtime result, and
  only when the supplied writer summon request matches the admitted immutable
  bytes and both writer/reviewer SDK request semantics and outputs; the
  reviewer state digest must still equal the exact result bytes initially
  admitted by the exporter. `landing_review` is bound at seed admission and
  again across result, task, durable state, and the final locked snapshot. The
  writer and reviewer session locks are retained while the seed, both summon
  request/schema pairs, and every exported writer/reviewer artifact are
  revalidated, the payload is rebuilt, and the A2A output is atomically written,
  so a concurrent continuation cannot mix verdicts or referenced bytes.
- records a digest-bound `yielding` parent state before `yield-parent` may
  launch Codex, preserves every partial yield attempt in a distinct directory,
  recovers a completed yield event without a second inference, ends the
  external Sol inference and process, evaluates the child result against the
  SDK wake policy without model polling, and uses `codex exec resume` through
  `reenter-parent` only for the exact parent thread when one bound event is
  significant; the child result must match its canonical durable runtime
  state/result/event receipt while the child session lock remains held through
  the parent admission event, but the admitted reference is its verified
  immutable attempt snapshot plus a pre-materialized digest-bound distilled
  return rather than the mutable canonical result; recovery uses only those
  admitted bytes. Parent yield and resume turns reject every tool item, and a
  crash after a valid re-entry event append
  is recovered only as a strict extension of the previously digested stream,
  with recognized terminal events replaying their filtered, failed, or
  completed semantic state; a pre-turn `reentering` crash resumes the same
  admitted child obligation, dead partial attempts are preserved before retry,
  and a completed digest-bound turn is recovered without a second inference;
  `reentry-status` observes the durable wait without inference.

Token counters contain only usage actually emitted by Codex. A controlled
interruption before `turn.completed` is therefore not represented as zero
work: the result marks `usage_observation.status=partial` and retains the exact
attempt/reason/event gap. A later exact-thread continuation adds newly observed
usage but does not fabricate the missing interrupted-attempt tokens.

`aoa-external-actor-bind` is the normal non-starting physical binding leaf. It
accepts already selected owner/SDK/model/runtime artifact paths, verifies the
runtime-profile-pinned owner schema bytes, hashes the workspace, Codex binary,
and every coordinate, writes one immutable `owner_contour` launch, and returns
control to `aoa-agents`. Its workspace-HEAD binding uses exact system Git under
a fixed minimal environment, never an ambient `PATH` resolution. It does not
detect an obligation, choose a role or
model, form the owner execution request, or start the actor. `aoa-summon` then
forms the separate semantic request and calls `preflight`, `start`, or
`run-to-terminal` with both exact paths.

The runtime admits model-neutral exact aliases for the initial model-organ
contours:
`landing-readonly-v2` binds the independent reviewer realization,
`landing-workspace-write-v2` binds the writer realization, while
`structured-owner-duty-workspace-write-v1` binds an already selected task-local
role for bounded eval, stats, or memo canaries. All three expose the same
isolated projection posture as their corresponding generic read or write
contour; the names preserve model-organ ABI and do not select a role, model,
procedure, route, or acceptance outcome.

`prepare_landing_study.py prepare-reviewer` is the canonical non-starting
review preparation path for both historical transport-study writers and admitted
owner-contour writers. It accepts an exact terminal read-only or bounded
repo-mutation writer, verifies the runtime-owned actor final manifest and
canonical delta, forwards every original immutable input under the same stable
ID, and adds the exact result, report, source baseline, actor final manifest,
and actor delta. A mutation writer
must name an explicit plan-bound reviewer contract and same-model/same-effort
read-only realization; the reviewer never inherits coder permissions. The
preparer compiles a distinct reviewer task, plan, binding, session, and launch
with observe-only usage metering, carries the writer's source-evidence scope
without widening its mutation scope, and starts no process.
For an evidence-complete `owner_contour` writer compiled before the baseline
manifest and SDK request schema became mandatory task inputs, the preparer may
derive `writer-source-baseline-manifest` from the digest-bound canonical
runtime state and `writer-summon-request-schema` from the exact selected SDK
schema. Those new IDs describe reviewer inputs; they never backfill or rewrite
the writer task. The reviewer receives its own active `summon-request-schema`,
and A2A export requires both schema copies to remain byte-identical under the
reviewer lock. An early owner plan may also carry a typed summon request and a
generic summon decision only when that exact decision remains bound as writer
task, snapshot, and continuation evidence. Every mismatch fails closed.
It also builds a fresh canonical reviewer summon request/decision against the
same exact SDK v4 schemas while retaining the writer request as immutable
evidence; it never substitutes either request with the runtime-owner task.
The prepared reviewer remains a separately addressed read-only fixture whose
role and realization must match the writer plan; A2A export admits only the
historical fixture pair or this exact owner-contour-writer/prepared-reviewer
pair.

The first live L2 fixture proved both branches. One invalid Luna report was
preserved and filtered with no second Sol turn. A corrected Luna xhigh report
produced `run.authority_required`, after which the exact yielded Sol thread was
resumed with a distilled, child-result- and event-digest-bound return. This is
transport evidence only; it does not admit Luna or establish net benefit.

All commit, push, PR, merge, tag, release, publication, service, secret, and
global-config effects remain disabled in this first admission. A green runtime
fixture proves the transport and guards; it does not prove Luna's landing fit
or net benefit.

For MCP-bearing read roles, the worker keeps the real owner bearer outside the
Codex process and injects it through an attempt-local loopback relay. Codex sees
only a random, expiring proxy path and no bearer environment variable; its
model-issued commands run under the Codex 0.147 bubblewrap backend with private
PID and network namespaces because legacy Landlock fallback is explicitly
disabled for this bounded filesystem posture. Thus procfs remains usable for
ordinary process work without exposing the upstream role credential. The
runtime does not claim exhaustive path-alias classification from command events
that omit effective working directory. Streaming MCP events are forwarded
incrementally, and active authenticated relay sockets and handlers are
terminated before the attempt can reach terminal finalization.

## Machine-local installation

`install_external_codex_runtime.py` installs exact runtime bytes, the
`aoa_sdk` Python package, SDK-owned incarnation plus summon v4 schemas, and the
pinned `aoa-agents` execution-request plus `aoa-skills` task-local-DAG schemas
as one immutable content-addressed release below
`/srv/abyss-machine/runtimes/abyss-stack/external-codex-agent/releases/`.
It atomically updates a regular-file `active.json` receipt and three stable
non-symlink wrappers in `~/.local/bin`:

- `aoa-external-codex-agent` for the runtime controller;
- `aoa-external-actor-bind` for model-neutral launch binding;
- `aoa-external-codex-study` for the canonical study preparer.

Host-admitted canaries use a two-phase path instead of `install`. `stage`
materializes and records the exact immutable release without writing
`active.json` or publishing any wrapper. After `abyss-machine` has built,
signed, verified, promoted, materialized, re-promoted, and admitted that exact
release-manifest subject, `activate-admitted` runs a fresh fixed-argument
`runtime_canary` trust-gate query itself. It recomputes the subject aggregate
from the staged release manifest and requires the gate's latest record, source
commit, host-managed trust root, verified controls, subject store, and record
identity to bind that same release before wrapper publication. The full gate
result and exact argv are retained in `active.json`; a denied, stale,
source-mismatched, dirty, or malformed admission leaves the release staged but
inactive.

Each installed wrapper is a minimal static x86_64 Linux ELF with no dynamic
interpreter. Before its first dynamic exec it removes every ambient `LD_*`
loader variable, derives its adjacent non-executable read-only Python
companion through `/proc/self/exe`, and starts that companion with fixed
`/usr/bin/python3 -I -B`. Installation, activation, and status build and
validate this launcher from the packaged assembly with fixed `/usr/bin/cc`;
therefore x86_64 Linux, that compiler coordinate, bubblewrap at
`/usr/bin/bwrap`, and unprivileged user/mount namespaces are host
prerequisites. Activation of a legacy immutable release whose manifest predates
the assembly uses the current landed installer's assembly only as an explicit
rollback-compatibility bridge; new releases bind the assembly inside their own
manifest.

The companion verifies the exact manifest closure, seals every verified file,
and asks bubblewrap to copy those descriptors into a private read-only tmpfs
root at `/mnt/aoa-external-codex-release`, a coordinate absent from the host
release tree. It then launches
the sealed selected Python from inside that snapshot in isolated,
bytecode-disabled mode through a release-local entrypoint that inserts only the
packaged SDK source before entering the runtime. Imports and adjacent schema or
module-digest reads therefore remain bound to the bytes already verified even
if the host release directory or its parent coordinate is replaced
concurrently. Ordinary wrapper execution also cannot add `__pycache__`
entries to the immutable release.
The packaged SDK subtree is
also a valid `--aoa-sdk-root` for study
preparation because it carries the exact non-Python contracts consumed there.
`status` rejects extra files, directories, symlinks, or missing entries,
re-hashes every released file, and verifies all three launcher/companion pairs.
`activate --release-id ...` remains the explicit local rollback path and does
not claim host artifact admission. `activate-admitted --release-id ...` is the
only path that records a fresh host canary verdict. Both retain later releases;
release IDs must be exact SHA-256 identifiers whose resolved
directory and manifest identity remain inside the release root. Installation
also verifies that the packaged `aoa-agents` and `aoa-skills` schema bytes have
the exact digests pinned by the runtime profile. Install, activation, and
status also require the recorded Python coordinate to remain a direct ELF
CPython 3.11-or-newer executable, proven by an isolated probe whose
`/proc/self/exe` identity must match the admitted file. Scripts and delegate
shims are rejected rather than trusting an unbound downstream interpreter.
Dirty worktree installation is
rejected unless every dirty source posture is explicitly admitted. This
includes index-hidden packaged files marked assume-unchanged or skip-worktree
and ignored files that would enter the packaged SDK; their path sets are
counted and digested in the source posture. Such an active receipt is marked
`nonproduction_dirty_source=true` and is machine-local evidence, not a landed
or remotely reproducible release. Before activating any materialized release,
the installer re-enumerates the selected inputs, requires unchanged Git
postures, and re-hashes every source byte against the release manifest; a
checkout race therefore fails before wrapper or active-receipt mutation.
Every installer posture probe uses the exact system Git under a fixed minimal
environment and a private metadata snapshot containing only the selected HEAD,
index, a read-only object-store alternate, and runtime-authored configuration.
When the selected index is split, its exact validated `sharedindex.<hash>`
backing file is copied into the same private snapshot. One non-following file
descriptor supplies both verification and copied bytes: the repository-format
digest must match the index footer and filename before those bytes are written.
Repository hooks, fsmonitor, filters, promisor lazy fetching, global/system
attributes, and source configuration never enter the posture process. Even a filter added to the
source `.git/config` after snapshot creation therefore cannot gain
installer-process execution before status or index inspection.
Installation requires clean exact
`abyss-stack`, `aoa-sdk`, `aoa-agents`, and `aoa-skills` source roots unless
each dirty posture is admitted explicitly.

See [CONTRACT.md](CONTRACT.md), [DIRECTION.md](DIRECTION.md),
[PROVENANCE.md](PROVENANCE.md), [SUSPENSION.md](SUSPENSION.md), and
[VALIDATION.md](VALIDATION.md).
