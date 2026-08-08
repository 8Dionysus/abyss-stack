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
  on the exact workspace through each active worker attempt so separate
  sessions cannot overlap their evidence or mutations, and runs Codex beneath a Linux
  parent-death/subreaper supervisor that
  adopts and cleans detached descendants without placing an outer namespace in
  front of Codex's own sandbox, while retaining exact PGID/SID TERM/KILL
  observation;
- keeps read-only target-workspace authority while running Codex from a distinct
  runtime-created attempt-local execution root; Codex's internal
  `workspace-write` sandbox can write only that execution root and its
  attempt-local `TMPDIR`, while the target checkout remains outside writable
  roots and network remains disabled;
- resumes only the exact durable thread and event cursor, with one explicit
  digest-bound follow-up route for an unchanged read-only review rejected only
  by an identity-field mismatch, and preserves every prior terminal result plus
  a digest-bound snapshot closure for all referenced evidence in its attempt
  directory before any admitted continuation;
- turns read-only drift, out-of-scope paths, forbidden effects, identity drift,
  or report-contract drift into typed failure or authority-blocked evidence;
  non-owner-fixed interpreter, script, process-launch wrapper, `find -exec`,
  `eval`, and `xargs`
  commands whose indirect effects cannot be classified are retained as
  counterevidence and authority-block the result, shell separators remain
  visible even when attached to arguments, redirection remains an opaque
  authority signal, `env --split-string` cannot smuggle an executable past the
  observer, value-taking `timeout` options cannot hide the wrapped command,
  and commands are durably observed
  from `item.started` rather than only after completion, while exact task validation
  argv remain admitted by their owner-supplied identity;
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
  workspace-manifest digest observed when that command completed, preserves
  `review_required` as a real gate, distinguishes a non-review writer's
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
  admitted by the exporter, so a concurrent resume cannot mix verdicts.
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
control to `aoa-agents`. It does not detect an obligation, choose a role or
model, form the owner execution request, or start the actor. `aoa-summon` then
forms the separate semantic request and calls `preflight`, `start`, or
`run-to-terminal` with both exact paths.

`prepare_landing_study.py prepare-reviewer` remains the canonical non-starting
transport-study review preparation path. It accepts an exact terminal read-only or bounded
repo-mutation writer, verifies the runtime-owned final workspace manifest,
forwards every original immutable input under the same stable ID, and adds the
exact result, report, and a distinct post-writer manifest. A mutation writer
must name an explicit plan-bound reviewer contract and same-model/same-effort
read-only realization; the reviewer never inherits coder permissions. The
preparer compiles a distinct reviewer task, plan, binding, session, and launch
with observe-only usage metering, carries the writer's source-evidence scope
without widening its mutation scope, and starts no process.
It also builds a fresh canonical reviewer summon request/decision against the
same exact SDK v4 schemas while retaining the writer request as immutable
evidence; it never substitutes either request with the runtime-owner task.

The first live L2 fixture proved both branches. One invalid Luna report was
preserved and filtered with no second Sol turn. A corrected Luna xhigh report
produced `run.authority_required`, after which the exact yielded Sol thread was
resumed with a distilled, child-result- and event-digest-bound return. This is
transport evidence only; it does not admit Luna or establish net benefit.

All commit, push, PR, merge, tag, release, publication, service, secret, and
global-config effects remain disabled in this first admission. A green runtime
fixture proves the transport and guards; it does not prove Luna's landing fit
or net benefit.

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

Each wrapper launches Python in isolated mode through a release-local
entrypoint that inserts only the packaged SDK source before entering the
runtime. The packaged SDK subtree is also a valid `--aoa-sdk-root` for study
preparation because it carries the exact non-Python contracts consumed there.
`status` rejects extra files, directories, symlinks, or missing entries,
re-hashes every released file, and verifies all three wrappers.
`activate --release-id ...` provides release rollback without deleting later
releases; release IDs must be exact SHA-256 identifiers whose resolved
directory and manifest identity remain inside the release root. Installation
also verifies that the packaged `aoa-agents` and `aoa-skills` schema bytes have
the exact digests pinned by the runtime profile. Install, activation, and
status also require the recorded Python coordinate to remain a regular
executable compatible CPython 3.11-or-newer interpreter, proven by an isolated
probe rather than the executable bit alone. Dirty worktree installation is
rejected unless every dirty source posture is explicitly admitted. This
includes index-hidden packaged files marked assume-unchanged or skip-worktree
and ignored files that would enter the packaged SDK; their path sets are
counted and digested in the source posture. Such an active receipt is marked
`nonproduction_dirty_source=true` and is machine-local evidence, not a landed
or remotely reproducible release. Installation requires clean exact
`abyss-stack`, `aoa-sdk`, `aoa-agents`, and `aoa-skills` source roots unless
each dirty posture is admitted explicitly.

See [CONTRACT.md](CONTRACT.md), [DIRECTION.md](DIRECTION.md),
[PROVENANCE.md](PROVENANCE.md), [SUSPENSION.md](SUSPENSION.md), and
[VALIDATION.md](VALIDATION.md).
