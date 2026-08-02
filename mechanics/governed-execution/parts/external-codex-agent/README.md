# External Codex Agent

This part is the `abyss-stack` runtime owner for one explicitly bound Codex
incarnation running as a separate operating-system process. It is not Codex's
built-in subagent transport, a TUI-injection layer, a model router, or an
authority for role meaning, model fit, eval verdicts, owner acceptance, or
landing effects.

The first admitted family is deliberately narrow: landing readiness,
preparation, independent review, closeout, and ambiguity-stop work. Exact
`gpt-5.6-luna` max/xhigh and a `gpt-5.6-sol` max comparison baseline may enter
only through owner-qualified `aoa-models` realizations and a post-compile
`aoa-sdk` `AgentIncarnationBinding`.

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
  settings, no inherited MCP servers, no network in the admitted tool profiles,
  and a structured final-output schema whose session-local derivative fixes the
  exact task and incarnation identities before inference;
- persists normalized events, exact thread identity, attempts, PIDs/start
  ticks, argv, usage, active wall time, output bytes, workspace changes,
  the exact final workspace manifest, wake evaluation, and a typed terminal
  result beneath an explicit state root;
- exposes asynchronous `start` for durable owner-managed sessions and
  `run-to-terminal` for transient cgroup launchers that must keep their main
  process alive until the exact semantic terminal receipt, without adding a
  time, token, turn, output, command, cost, or memory budget;
- rebuilds the exact byte-level workspace manifest at finalization, drains a
  terminal process stream before finalization, counts tokens/turns/time/output
  without imposing execution budgets, includes ignored workspace bytes without
  reading secret-shaped ignored inputs, and runs Codex beneath a Linux
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
  by an identity-field mismatch, and preserves every prior terminal result in
  its attempt directory before any admitted continuation;
- turns read-only drift, out-of-scope paths, forbidden effects, identity drift,
  or report-contract drift into typed failure or authority-blocked evidence;
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
- binds every validation claim to an exact observed argv/exit state, preserves
  `review_required` as a real gate, distinguishes a non-review writer's
  `submit_for_review` handoff from a reviewer's `return_for_repair` verdict,
  binds each negative review to a separate task-owned outcome status,
  binds model re-entry to the status-selected wake condition, admits only
  genuinely produced workspace artifacts, and rejects unbound `owner_contour`
  labels;
- exports an A2A-compatible child result only after a different incarnation
  and different Codex thread reviewed the exact writer runtime result, and
  only when the supplied writer summon request matches the admitted immutable
  bytes and both writer/reviewer SDK request semantics and outputs.
- records a digest-bound parent continuation with `yield-parent`, ends the
  external Sol inference and process, evaluates the child result against the
  SDK wake policy without model polling, and uses `codex exec resume` through
  `reenter-parent` only for the exact parent thread when one bound event is
  significant; `reentry-status` observes the durable wait without inference.

Token counters contain only usage actually emitted by Codex. A controlled
interruption before `turn.completed` is therefore not represented as zero
work: the result marks `usage_observation.status=partial` and retains the exact
attempt/reason/event gap. A later exact-thread continuation adds newly observed
usage but does not fabricate the missing interrupted-attempt tokens.

`prepare_landing_study.py prepare-reviewer` is the canonical non-starting
review preparation path. It accepts an exact terminal read-only or bounded
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
`aoa_sdk` Python package, and the SDK-owned incarnation plus summon v4 schema
closure as one immutable content-addressed release below
`/srv/abyss-machine/runtimes/abyss-stack/external-codex-agent/releases/`.
It atomically updates a regular-file `active.json` receipt and two stable
non-symlink wrappers in `~/.local/bin`:

- `aoa-external-codex-agent` for the runtime controller;
- `aoa-external-codex-study` for the canonical study preparer.

Each wrapper launches Python in isolated mode through a release-local
entrypoint that inserts only the packaged SDK source before entering the
runtime. The packaged SDK subtree is also a valid `--aoa-sdk-root` for study
preparation because it carries the exact non-Python contracts consumed there.
`status` re-hashes every released file and verifies both wrappers.
`activate --release-id ...` provides release rollback without deleting later
releases. Dirty worktree installation is rejected unless both dirty source
postures are explicitly admitted; such an active receipt is marked
`nonproduction_dirty_source=true` and is machine-local evidence, not a landed
or remotely reproducible release.

See [CONTRACT.md](CONTRACT.md), [DIRECTION.md](DIRECTION.md),
[PROVENANCE.md](PROVENANCE.md), [SUSPENSION.md](SUSPENSION.md), and
[VALIDATION.md](VALIDATION.md).
