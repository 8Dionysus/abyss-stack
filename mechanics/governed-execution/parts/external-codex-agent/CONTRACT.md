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
The packaged SDK root must therefore satisfy both isolated imports and the
preparer's exact non-Python contract reads. Stable wrappers consult a regular-file active
receipt and execute a release-local bootstrap with Python isolated mode; they
do not follow a mutable source checkout, import ambient `PYTHONPATH`, or use a
symlinked `current` directory. `install_external_codex_runtime.py status`
re-hashes the release and wrappers before availability may be claimed.
Activation rollback changes only the active receipt while retaining immutable
releases.

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
observe the persisted session. `run-to-terminal` starts the same durable
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
   available, and a disposable parent-death/subreaper containment probe
   succeeds before inference;
8. the workspace is an exact Git worktree at the pinned HEAD and requested
   clean/exact baseline, selected by one explicit immutable manifest input ID;
9. every additional immutable input is pinned by the continuation and copied
   into the private runtime state before the model sees it;
10. every task validation command ID is unique, and the final report covers the
   exact fixed command sequence with a non-empty evidence reference for every
   passed, failed, or skipped claim; each claimed status must equal the final
   runtime-observed exit state of an exact argv execution;
11. `transport_study_fixture` is admitted only as bounded compatibility
    evidence. `owner_contour` additionally requires a separate exact
    `aoa-agents` `summon-request-v3`, validated against its runtime-profile-
    pinned owner bytes, whose obligation, mandate, ready task-local DAG,
    accepted responsibility transfer, domain procedure refs, child scope,
    external-process/session posture, and observe-only usage semantics match
    the launch and continuation exactly.

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

Semantic profiles admit only `read-only` or bounded `workspace-write` target
authority with model-shell network disabled. A role-scoped read profile may
configure exactly one loopback AoA MCP (`aoa_evals`, `aoa_stats`, or
`aoa_memo`) from its own required bearer-token environment variable. The
token is passed to the Codex MCP client configuration but excluded from the
model shell; ambient MCPs and the other role servers remain absent. For
`read-only`, the runtime does not make the target
checkout the Codex writable root. It creates a distinct attempt-local execution
root, launches Codex's internal `workspace-write` sandbox there, and sets
`TMPDIR` to the sibling attempt-local scratch directory. The target checkout is
passed separately as the exact repository under study and remains outside all
writable roots. This lets test runners create ephemeral capture/temp files
without granting target-workspace mutation authority. The invocation receipt
records the actual execution root, and overlap between that root and the target
fails closed. For semantic `workspace-write`, Codex instead uses the exact
target checkout as its execution root, and a reviewed local preparation may be
made inside task `allowed_paths`. Those paths govern mutation and declared
workspace artifacts; they do not double as the source-evidence boundary. The
optional `source_evidence_paths` field governs anchored workspace citations and
falls back to `allowed_paths` only for older v1 tasks. Neither field authorizes
commit, push, PR, merge, tag, release, publication, service mutation, secret
access, or global config mutation.

Codex runs beneath a Linux supervisor that owns a separate process group but
does not create an outer user or PID namespace. This leaves Codex's own
`codex-linux-sandbox`/bubblewrap namespace construction intact. Before it
launches Codex, the supervisor verifies the exact worker PPID, enables
`PR_SET_CHILD_SUBREAPER`, requests `SIGTERM` through `PR_SET_PDEATHSIG`, and
checks the PPID again to close the parent-death setup race.

On normal exit, controlled termination, or worker death, the supervisor adopts
or enumerates the exact descendant closure in `/proc`, checks PID start ticks,
and applies bounded TERM then KILL cleanup. This includes TERM-resistant
descendants that call `setsid`. An attempt-local interrupt request binds the
signal to the session, attempt, supervisor PID, and process start ticks; only
then may the worker finalize an `interrupted` receipt suitable for exact-thread
resume. Unexpected worker death produces a typed failed result and is not
misrepresented as a controlled checkpoint.

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
than comparing only
porcelain status. Same-status byte changes, ignored and untracked bytes, path
kind, symlink target, size, binary diff, and HEAD drift therefore remain
observable. An untracked or ignored secret-shaped path blocks admission before
its content is hashed. Read-only manifest drift, HEAD drift, an out-of-scope
write, or a command event whose command text is unavailable fails closed as
`authority_blocked` evidence. The command observer recognizes wrapped/scoped
Git and GitHub effects plus publication, service, secret-access, and global
configuration command families; the sandbox remains the primary effect
boundary, and command observation is retained as auditable counterevidence.

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

Before every admitted resume, the controller validates the current terminal
`result.json`, copies its exact bytes into the prior attempt directory, and
adds that immutable reference to the continuation's event/evidence chain. A
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
  report, and runtime-owned final-workspace-manifest digests;
- exact writer and reviewer final-workspace-manifest artifact digests;
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
schema bytes. It starts a distinct `gpt-5.6-sol` max process with built-in
multi-agent behavior disabled and requires one structured yield report. After
`turn.completed`, that process exits; the controller persists the parent Codex
thread and a `waiting` state. No model inference or model-driven polling remains
alive while the child works.

`reenter-parent` admits only the exact terminal child result named by the
obligation and binding. It revalidates the child's task, incarnation, result
schema, event-stream digest, evidence inclusion, continuation, return owner,
deferred decisions, and status-selected SDK wake condition. Exactly one
`external_agent.wake_evaluated` event must match the runtime result. Failed,
missing, false, duplicate, or non-parent events are preserved and filtered
without a second Sol turn.

When and only when the admitted event selects `wake_parent`, the controller
builds a compact return bound to the child-result and observed-event digests,
then invokes `codex exec resume <exact-parent-thread-id>`. The resumed Sol must
return a typed parent-reentry report whose identities and authority action
match that return. A successful cycle therefore has two completed turns on one
parent thread with an inference-free durable wait between them. Re-entry
failure is terminal evidence and is never automatically retried.

This use of the current Codex exact-thread resume surface proves the product
transport needed by L2; it does not make Codex the owner of wait significance,
role truth, model fit, proof, acceptance, or effects. Those remain with the
binding/runtime and their named owner surfaces.

The export is only a `child_task_result` candidate for the existing
`agent-os-adapter` A2A return-review lane. That downstream lane still requires
the exact summon request and decision chain. Neither export nor downstream
review is an eval verdict, owner acceptance, landing, or proof of benefit.
