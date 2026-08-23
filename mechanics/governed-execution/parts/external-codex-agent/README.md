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
- prepares an incarnation-scoped Codex home for operator-visible external
  actors. The canonical visible holder and its descendants use the projected
  incarnation home; authentication, session continuity, and actor tooling are
  retained through typed shared links, while ambient operator-control and
  unknown entries are not inherited. The launcher binds model and effort
  explicitly and passes the same scoped home through Codex's shell environment
  policy, so ordinary descendant `codex exec` processes retain the selected
  incarnation. A direct visible holder can additionally
  emit its own PID/start-ticks/post-exec-argv-bound lifecycle receipt immediately
  before `exec`, including the first detached Kitty ancestor, its window identity,
  and a no-sibling dedication proof across the installed bubblewrap wrapper;
  for a shebang launcher, an internal payload handoff writes that receipt from
  the exact bubblewrap payload PID immediately before replacing itself with the
  private launcher; the bubblewrap monitor remains only the snapshot-cleanup
  supervisor. The receipt includes the exact launch-time incarnation manifest
  bytes as a digest-bound base64 snapshot; after launch, its pathname is
  provenance only, so profile preparation may refresh that pathname without
  changing holder identity. The installed launcher closes that exact holder
  terminal only after typed closure authorization. Authorization may be
  `wake_delivered` (a separate wake receipt proves delivery) or
  `join_completed` (a non-waking join proves a returned responsibility); both
  forms bind the exact holder receipt, handoff, closure path, PIDs, and
  required `close_exact_bound_holder` action. The join receipt, semantic
  re-entry, owner acceptance, and master wake remain separate claims. The
  produced handoff must bind both receipt paths under
`runtime.responsibility_holder`, while the evidence receipt binds the SHA-256
 of the exact handoff bytes. Join and wake authorization validate a pinned
 handoff snapshot and recheck it immediately before publishing the authority;
 after delivery or join, a host-side bridge may
  run the closer in the same host unit. A detached visible launch is admitted
  only with an owner binding context and a unique private Kitty control socket
  in socket-only mode. The owner `status` command validates the bound
  PID/start-tick identities and queries Kitty through that socket using a safe
  allowlist. Its output excludes raw Kitty `ls` payloads, environment, command
  lines, tokens, and credentials; compositor visibility remains explicitly
  unknown. `send-text` is a separately invoked terminal transport, not A2A
  responsibility transfer. The holder receipt also binds the kernel boot ID
  alongside each process start tick. The closer publishes a
  recoverable sidecar reservation before signaling. The sidecar records the
  signal attempt before TERM and recovery never repeats an existing attempt;
  legacy v1 reservations remain replayable only through the legacy
`--wake-receipt` route, while new reservations use v2. V2 reservations bind
the authorization and wake/join evidence byte digests, and replay rejects
either file's byte drift. Completed v1 closure receipts remain schema-valid
and replay only through their matching legacy wake reservation. A retry after a join
  write reuses the exact canonical join evidence before publishing missing
  authorization, and the sidecar keeps the authorization file reference
  distinct from its actual wake/join evidence reference; a replayed
  authorization must bind the exact join path and digest, so a concurrent or
  mismatched join cannot inherit another join's close authority;
  state and final receipts are atomically published with their containing
  directory fsynced before lifecycle progress, and replay of an unclosed
  receipt remains failed. A recovery retry uses a newly bound closure target
  and preserves the prior failed receipt bytes. Direct ELF launch uses an
  inheritable sealed memfd
  when no adjacent Codex companion exists. If the named
  `codex-code-mode-host` companion is present, the runtime seals both exact
  ELF files and materializes them beside each other in one private read-only
  package coordinate; the holder receipt records the companion digest and
  package-relative coordinate.
  Direct shebang launch first builds a private filesystem-rooted package-layout
  mirror, then reopens every copied directory and regular file to verify its
  device/inode and bytes. Each verified regular file is copied into a sealed
  memfd; bubblewrap materializes those sealed bytes into the matching
  package-relative tree in a private `/var/tmp` tmpfs, applies the admitted
  modes, and remounts that tree read-only before both version probing and final
  exec. With a holder receipt, the payload helper revalidates the manifest and
  private launcher digests inside the namespace before writing the receipt;
  bubblewrap also binds the payload lifetime to its parent. This execution
  coordinate cannot be renamed or chmodded by the same-UID holder. The mirror preserves the launcher's `$0`/module-relative
  coordinate, including parent-relative paths such as `bin/` launchers
  resolving `../vendor`. Source-ancestor links are retained only outside the
  detected package boundary; the package subtree is copied without writing to
  a root-owned installed package. The host snapshot lives under the admitted
  `codex_home/tmp` local directory, and its filesystem is rejected when marked
  `noexec`; it remains lifecycle cleanup evidence rather than the mutable
  final execution coordinate. A lifecycle child removes the exact snapshot and
  mirror after the holder's PID/start-tick identity exits. Both routes execute
  the exact admitted bytes rather than mutable source-inode bytes or a
  replaceable source pathname, and the named route remains reopenable for
  Node-backed `#!/usr/bin/env node` launchers. A naturally exited exact pair is
  recorded as `already_gone` without marker
  reconstruction.
  This identity is
  distinct from any nested proof actor. This operator surface is not A2A transport and
  does not replace the governed JSONL runtime;
- records the v2 incarnation-home manifest as a model-neutral capability
  projection. Session continuity and actor tooling entries remain available by
  default, while ambient operator-control entries and unknown entries are
  denied rather than admitted by an endpoint blacklist. An owner-authored
  `external-codex-capability-grant.schema.json` grant may project exactly one
  operator-control entry only when its capability ID, ambient-home identity,
  model realization, incarnation coordinate, digest, and expiry match. This
  projection controls runtime materialization; it is not itself an
  app-server mutation gate or owner-acceptance proof;
- exposes the installed `aoa-external-codex-return` leaf for the final external
  return contour. The leaf receives an explicit return-owner binding and exact
  handoff/holder paths, uses a connectable local Codex app-server as a
  replaceable transport, records accepted delivery for either a paused or
  active Goal through bounded turn views without treating omitted history as
  idle, and composes typed authorization with exact holder closure. It does not
  claim owner acceptance or semantic re-entry;
- exposes the separate `aoa-external-codex-return pause` lifecycle action. It
  receives a pause-owner binding and requires an `atomic_goal_transition`
  adapter method that performs a server-supported compare-and-set/version proof
  before performing the Codex app-server Goal transition from `active` to
  `paused`. The installed public
  `ThreadGoalSetParams` method lacks that proof, so the canonical adapter fails
  closed before mutation until a protocol-capable adapter is supplied. A
  distinct pause receipt binds the typed transition proof; pause, wake delivery,
  holder closure, semantic re-entry, and owner acceptance remain separate
  events and claims;
- exposes `aoa-external-codex-stasis` as a generic, model-neutral responsibility
  movement observer. It consumes one exact lifecycle/session evidence snapshot,
  requires a matching lifecycle transition before classifying movement, and
  applies a bounded cost-aware one-shot check. A due missing transition emits a
  typed stasis event and review wake for the exact return owner; process
  existence, hook-screen state, domain failure, Goal acceptance, automatic
  kill/restart, and unrelated-actor mutation are never substitutes for
  transition evidence;
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
  binaries. Independent preflight probes overlap only as separate
  start-new-session supervisor process groups: admission waits for every exact
  result, retains each probe's deadline and failure class, and terminates and
  reaps every outstanding group if one cannot complete. The controller still
  repeats the complete preflight in the worker and records the exact
  mount-wrapper and mount-launcher digests for defense-in-depth drift checks;
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
  by an identity- or task-owned transition-field mismatch and for an
  authority-safe bounded writer rejected only during model-report admission;
  an exact pre-turn provider-capacity failure has a third same-role route only
  when its result-bound raw Codex event stream proves the terminal usage-limit
  pair, zero observed work/effects, and unchanged source/projection state.
  Writer report repair requires
  unchanged owner source, complete actor manifest/delta evidence, and every
  observed change inside the original allowed paths; it retains the original
  role and authority envelope. Every route preserves each prior terminal result plus
  a digest-bound snapshot closure for all referenced evidence in its attempt
  directory before any admitted continuation. A continuation can add exact
  inline UTF-8 evidence with a stable ID and provenance digest: the controller
  reads no arbitrary host path, validates all entries before writing, preserves
  controller bytes, gives the actor only a sanitized immutable envelope, and
  expands only the session-local evidence schema. It does not widen role,
  workspace, tools, effects, or external authority;
- emits result v2 with mandatory actor/source provenance for successful returns,
  while continuing to read legacy result v1 and durable state v1/v2 for status and
  terminal-result recovery, while refusing a new inference attempt unless a
  safe v3-or-newer runtime-owned projection and its baseline are available;
- turns read-only drift, out-of-scope paths, forbidden effects, identity drift,
  or report-contract drift into typed failure or authority-blocked evidence;
  non-owner-fixed interpreter, script, process-launch wrapper, `find -exec`,
  `eval`, and `xargs`
  commands whose indirect effects cannot be classified are retained as
  counterevidence and authority-block the result by default. A task may instead
  admit `sandbox_confined` local indirection only when the exact incarnation
  binding proves a matching read-only or workspace-write sandbox, approval
  `never`, disabled network, and no secret or external-effect authority;
  fixed landing-track packets may bind that policy into a bounded writer task,
  while canonical landing-review preparation binds it into its newly generated
  read-only task rather than inheriting the writer task's policy;
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
  symbolic anchors on that JSON artifact name either an exact top-level member
  or an exact `content_entries[].path`, never an arbitrary byte substring,
  while bounded line anchors retain their ordinary meaning;
- before an independent reviewer starts, closes any nested writer evidence
  graph through the exact admitted producer task, result, report, actor delta,
  final manifest, upstream actor envelopes, validation observations, and
  anchored historical source bytes. Exact historical final-manifest line,
  member, content-entry, and delta-bound output anchors remain admissible. An
  incomplete producer envelope retains the unchanged model-only route instead
  of exposing a partial namespace. The controller exposes the resulting
  read-only derivative as `runtime:nested-evidence-namespace#<entry-id>`. The
  prompt carries only a compact digest-bound summary and exact read-only
  materialized path; the reviewer selects needed entries from the full JSON
  with bounded queries instead of repeating every excerpt on every tool turn;
  digest collisions, ambiguity, drift, or an invalid anchor fail before model
  inference. The namespace never rewrites the signed/content-addressed writer
  artifact and never replaces source or owner authority;
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
  accepted responsibility transfer, domain procedure refs, exact SDK run-plan
  and model-realization refs, and pinned owner schemas;
- exports an A2A-compatible child result only after a different incarnation
  and different Codex thread reviewed the exact writer runtime result, and
  only when the supplied writer summon request matches the admitted immutable
  bytes and both writer/reviewer SDK request semantics, non-empty plan-bound
  capabilities, and outputs; the
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
and every coordinate, verifies the selected runtime package root and its
profile-pinned aggregate/member subject plus digest-bound identity/subjects
sidecars, writes one immutable `owner_contour`
launch, and returns control to `aoa-agents`. Its workspace-HEAD binding uses
exact system Git under a fixed minimal environment, never an ambient `PATH`
resolution. It does not
detect an obligation, choose a role or
model, form the owner execution request, or start the actor. `aoa-summon` then
forms the separate semantic request and calls `preflight`, `start`, or
`run-to-terminal` with both exact paths.

The runtime admits model-neutral exact aliases for the initial model-organ
contours:
`landing-readonly-v2` binds the independent reviewer realization,
`landing-workspace-write-v2` binds the writer realization, while
`landing-workspace-write-preview-v1` binds a writer whose selected bounded-change
plan also owns the read-only preview step, and
`structured-owner-duty-workspace-write-v1` binds an already selected task-local
role for bounded eval, stats, or memo canaries. All listed aliases expose the
same isolated projection posture as their corresponding generic read or write
contour; the names preserve model-organ ABI and do not select a role, model,
procedure, route, or acceptance outcome.

`prepare_landing_study.py prepare-writers` is also package-bound: callers must
provide one exact runtime package root, its digest-bound artifact identity and
artifact subjects sidecars, and the selected `bin/codex` executable. The
preparer validates those coordinates against the runtime profile and emits the
same `runtime_package` binding on every transport-study writer launch. Reviewer
preparation forwards that package and the writer's exact runtime-profile
coordinate unchanged.

At process containment, the admitted host `package_root` is verification input,
not the execution coordinate. The supervisor materializes the complete package
view in the private runtime-owned
`/var/tmp/aoa-external-actor-runtime-package` tmpfs and launches `bin/codex`
from that coordinate, so a same-UID rename or replacement of the host package
root cannot redirect package-relative helper lookup after mount setup.

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
The reviewer specialization's exact `aoa-agents` capability pack is added to
the scenario, selected on the active review step, and repeated by identity in
the canonical SDK summon request. If the writer already is the reviewer role,
the preparer instead retains the single capability named by its exact SDK
request and admitted scenario; an absent or ambiguous match fails. Existing
non-review steps and capabilities remain unchanged. Runtime preflight requires
the writer and reviewer summon
capability sets to be non-empty subsets of their admitted plans, so a session
that cannot later produce a valid A2A return never begins inference. The same
preflight also binds the request's role, incarnation, parent task, session,
named outputs, transport, review posture, and workspace to the exact launch and
runtime task; these semantics are not deferred until A2A export.
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

The role-first path is stronger and separate from that compatibility preparer.
When `aoa-agents` supplies a complete independent reviewer obligation and owner
execution request, both writer and reviewer remain `owner_contour`. The generic
A2A branch then requires distinct threads and incarnations, an immutable copy
of the exact writer task/result/report and every report-named output, matching
owner and parent relations, read-only zero-delta review, and exact SDK v4
request/schema bytes under the final writer/reviewer locks. Its payload names
`owner_contour_immutable_evidence`; it returns responsibility without claiming
domain acceptance or model fit. Non-landing reviewer preparation uses neutral
review family/output names rather than reusing landing semantics.

The first live L2 fixture proved both branches. One invalid Luna report was
preserved and filtered with no second Sol turn. A corrected Luna xhigh report
produced `run.authority_required`, after which the exact yielded Sol thread was
resumed with a distilled, child-result- and event-digest-bound return. This is
transport evidence only; it does not admit Luna or establish net benefit.

All commit, push, PR, merge, tag, release, publication, service, secret, and
global-config effects remain disabled in this first admission. A green runtime
fixture proves the transport and guards; it does not prove Luna's landing fit
or net benefit.

For MCP-bearing read roles, the installed CLI removes the real owner bearer
from its exec-time environment during one clean re-exec, carries the exact
bytes through a bounded sealed descriptor, and injects them only through an
attempt-local loopback relay. For MCP-bearing roles the runtime explicitly
enables Codex 0.148's `mcp_2026_07_28` client mode. The relay admits only an
already-modern `2026-07-28` request and preserves that exact version on the
authenticated upstream hop; it does not relabel legacy client traffic. Codex sees
only a random, expiring proxy path and
no bearer environment variable; actor filesystem permissions deny `/proc`,
while the controller retains host PID coordinates for exact lifecycle and
cleanup receipts. The model-issued commands still run under the Codex 0.148
bubblewrap backend with legacy Landlock fallback explicitly disabled. The
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
When a tool profile names a specialized environment, the same release also
contains its version-pinned Python package roots and the tracked files of each
exact owner snapshot. The first landing environment binds pytest, the packaged
`aoa_sdk`, and a clean `aoa-stats` source ref. The child receives their
release-snapshot coordinates as a composed `PYTHONPATH` and `AOA_STATS_ROOT`,
with pytest's cache provider disabled so fixed validation cannot leave actor
workspace residue; it does not inherit the user's Python site, mutable owner
checkout, or general host paths. These bytes provide tools
only: `aoa-stats` keeps validator and measurement authority.
It atomically updates a regular-file `active.json` receipt and four stable
non-symlink wrappers in `~/.local/bin`:

- `aoa-external-codex-agent` for the runtime controller;
- `aoa-external-actor-bind` for model-neutral launch binding;
- `aoa-external-codex-incarnation` for an operator-visible actor whose nested
  Codex processes inherit the selected incarnation defaults;
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
loader variable and starts its own embedded Python bootstrap with fixed
`/usr/bin/python3 -I -B`. The embedded payload binds the exact digest of the
atomically published `active.json`; it opens no adjacent companion pathname.
Installation, activation, and status build and
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
each dirty posture is admitted explicitly. A specialized owner snapshot such
as `aoa-stats` must always be clean and match the source ref pinned by the tool
profile; it has no dirty-source override.

Owner-contour launch binding also carries an owner-request-bound receipt
identity mode. New sessions use `stable_request_ref_v1`; pre-upgrade v3
receipts are recognized only by an exact legacy launch without that mode.
Runtime reads verify the materialized launch digest, the owner request semantic
self-digest, its `runtime_launch_ref`, and a separate non-replacing generation
anchor under `owner-admission-generations/` before selecting either result
form. The anchor is published outside the session directory and retained as
evidence by new results. Its pathname is deliberately not claimed to be
same-UID immutable: deletion makes the session unusable. It cannot reopen the
legacy route because `migrate-legacy-owner-admission` also requires an exact
session/launch/request/request-ref entry from
`legacy-owner-admission-migrations.v1.json`, verified as part of the
content-addressed release and mounted into the controller's sealed read-only
snapshot. The installer accepts an operator inventory only through
`stage --legacy-owner-migration-catalog`; the authored default is empty. A
non-empty catalog cannot pass ordinary `install` or ordinary `activate`: only
`activate-admitted` may publish that release after the host artifact trust gate
binds its complete release manifest. New
admission requires the current mode, and ordinary reads never create a
migration. A cataloged markerless v3 session may publish its anchor only when
the operator-supplied expected digests and all durable bytes agree. The same
anchor then preserves the crash-before-first-attempt `prepared` recovery path.
For a new current-generation admission, a crash after anchor publication but
before `state.json` is idempotent: the exact retry reuses the recorded anchor
timestamp and the verified unpublished actor projection without deleting it.
The external anchor also binds the actor-baseline manifest digest, so a
same-UID rewrite of both the projection and its session-local manifest cannot
be adopted merely by changing session files. The retry additionally builds a
fresh, inode-pinned witness from the independently admitted source or exact
review seed and requires the recovered content and private Git body to match;
recreating the UID-owned anchor therefore cannot select substituted bytes.
This external digest binding is generation-anchor v2. Stable-request v1
anchors were never deployed and are rejected; deployed legacy-v3 sessions are
admitted only by the release-cataloged explicit migration, which publishes a
v2 anchor. Recovery never runs Git against the
mutable projection. All non-index private-Git bytes are compared with the safe
witness authority captured in memory before the staging inode receives its
public session pathname. Later mutation of that published witness cannot change
the comparison value. The recovered index is read through a pinned descriptor
and sealed in a memfd, and only its stage/flag meaning is interpreted against
the fresh witness with hooks and fsmonitor disabled. The mutable projection is
then inventoried again, so a concurrent config, attribute, or worktree rewrite
can fail closed without gaining controller-process execution. If the prepared event was
already appended, its complete event object, including the anchor-derived
timestamp, becomes the initial durable prefix rather than being duplicated. A
different identity, changed projection, or additional event is rejected.
After `state.json` exists, v2 reads continue to bind its baseline reference and
bytes to the generation anchor. An attempt-free `prepared` retry also rebuilds
the independent witness before spawning its first worker, closing the
state-saved/process-not-yet-created crash window.

See [CONTRACT.md](CONTRACT.md), [DIRECTION.md](DIRECTION.md),
[PROVENANCE.md](PROVENANCE.md), [SUSPENSION.md](SUSPENSION.md), and
[VALIDATION.md](VALIDATION.md).
