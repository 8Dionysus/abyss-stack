# Launch Bound Model Incarnations as External Codex Processes

- Decision ID: ABYSS-STACK-D-0108
- Status: accepted
- Date: 2026-08-01
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-01
- Surface classes: runtime boundary, model incarnation, persistent session, A2A return
- Stack lanes: source, runtime, review
- Mechanic parents: governed-execution
- Guard families: exact binding, owner provenance, process isolation, effect ceiling, durable resume, independent review
- Posture: accepted source-local runtime with reviewed nonproduction machine-local vertical proof; model fit and production admission remain external

Decision [ABYSS-STACK-D-0109](ABYSS-STACK-D-0109-admit-external-actors-through-role-first-owner-contours.md)
extends this process-boundary decision and supersedes only its fixture-only,
landing-first admission posture. The external process/session boundary remains
accepted; current owner admission law lives at the source surfaces named by
D-0109.

## Context

The SDK can describe a model-neutral plan and now bind one exact post-compile
role incarnation, but the existing Agent OS A2A lane intentionally reviews a
returned child result and does not launch the child. The first economical
external model route needs persistent Codex sessions, explicit Luna/Sol
realizations, event-shaped parent re-entry, and landing-oriented work without
collapsing these responsibilities into Codex's built-in subagent transport or
into the existing return reviewer.

The runtime must preserve `aoa-agents` role meaning, `aoa-models` realization
meaning, `aoa-evals` verdict authority, and target-owner acceptance. It must
also keep commit, push, merge, release, publication, and other external effects
disabled during the first proof cycle.

## Options considered

- Use Codex's built-in `spawn_agent` transport and treat its child receipt as
  the new model organ.
- Inject prompts into a running TUI and infer session identity from terminal
  state.
- Extend the existing `agent-os-adapter` A2A return-review lane so it also
  launches and manages the child.
- Add a separate governed-execution runtime part that consumes the exact SDK
  incarnation binding and later exports a reviewed return into the existing
  A2A lane.

## Decision

Add `external-codex-agent` as a separate `abyss-stack` runtime-owner part. It
launches `codex exec` as a distinct operating-system process, disables Codex
built-in multi-agent behavior, ignores ambient user configuration and exec
rules, binds an explicit model/effort/tool/sandbox profile, persists exact
thread and event state, and resumes only from a durable session/thread/cursor
triple.

The first task family is landing readiness, preparation, review, closeout, and
ambiguity-stop. Runtime admission requires exact SDK plan/incarnation bytes,
owner-qualified role and model refs, workspace and immutable-input digests,
observe-only usage metering, semantic stop conditions, and event-filtered wake
policy. A2A export requires a
different incarnation and Codex thread reviewing the exact writer runtime
result. The existing Agent OS adapter remains the downstream owner of summon
request/decision/return review.

The source schema keeps `owner_contour` visible as a future admission class,
but this first runtime admits only `transport_study_fixture`; a label alone
cannot promote C2 transport into owner-semantic authority. Required review is
a runtime gate, not report prose. Workspace proof includes ignored bytes while
refusing to hash secret-shaped ignored inputs. Process cleanup is bound to an
exact outer PGID/SID plus a profile-bound Linux subreaper supervisor. The
supervisor verifies its worker parent, requests `SIGTERM` through
`PR_SET_PDEATHSIG`, adopts orphaned descendants through
`PR_SET_CHILD_SUBREAPER`, and applies bounded identity-checked TERM/KILL cleanup
even when a descendant creates another session with `setsid`.

Steady-state supervision is signal-notified through a nonblocking self-pipe,
with a one-second nonblocking `waitid` reap fallback; procfs descendant scans
and the 50 ms cadence are confined to bounded cleanup. Model-authored `source:`
evidence is admitted only when the exact workspace file lies inside the
explicit `source_evidence_paths` and its optional line/symbol anchor exists;
mutation and produced-artifact authority remains separately bounded by
`allowed_paths`. The study
preparation receipt records the complete SDK module-path inventory again after
all plan and binding compilation.

An earlier source candidate placed Codex inside an outer user/PID namespace.
The first live post-repair Luna run showed that this prevents Codex's own
`codex-linux-sandbox`/bubblewrap probe from completing. The runtime therefore
must not pre-empt the namespace layer owned by Codex's sandbox. That failed
candidate remains portability counterevidence rather than a model-quality
result.

External effects remain disabled. Runtime success is execution evidence only;
model fit and net benefit still require `aoa-evals`, and landing acceptance
still requires the target owner and user.

The first machine-local activation packages exact runtime and SDK bytes under
one content-addressed release manifest. Stable user wrappers read an atomic
regular-file active receipt and execute only a release-local isolated-mode
bootstrap; there is no mutable source-path or symlink-current dependency.
Every installation records both Git HEADs and dirty postures and retains the
prior release for activation rollback. A dirty admitted installation is marked
nonproduction and proves only the local invocation contour. It does not close
the separate requirement for an addressable landed SDK commit and exact remote
CI pin.

The installed package must include the non-Python SDK contracts consumed by
study preparation and return review, not only the importable Python modules.
The first installed contour omitted the agent-incarnation binding and summon
request/result v4 schemas, so the installed preparer could not reproduce the
source-worktree route. That failure is packaging counterevidence. The corrected
immutable release
`sha256-d63cd178172f2f02682c539052e1fef70e9ec3fc07b784c0aaea0ea6caed920b`
packages those exact schemas beside the runtime and SDK modules. This closes
the machine-local ABI-package seam only; it does not imply landed-source or
remote-CI parity.

The parent side uses the same external-process boundary. A source-owned parent
obligation produces one structured Sol yield turn and then the process exits.
The runtime retains the exact parent thread, evaluates the child terminal
result through the SDK wake binding, filters non-significant events without
inference, and supplies only a digest-bound distilled return to
`codex exec resume <exact-parent-thread-id>`. This is the narrow current L2
transport; it does not introduce a generic scheduler or transfer event
significance to the model.

The runtime counts tokens, wall time, turns, output bytes, and commands but
does not enforce caller-authored execution budgets. Those measurements are
post-run evidence, not preconditions on agent initiative. Provider limits and
explicit operator interruption remain observable runtime events.
Host resource estimates may admit or defer a safe launch, but do not become an
execution ceiling once the incarnation is admitted.

Codex token fields are counted only when the protocol emits
`turn.completed`. A controlled interruption before that point produces a
typed partial-usage observation rather than a false zero-work claim. Exact
thread continuation accumulates later observed usage without fabricating the
missing portion. Every admitted resume first preserves the prior terminal
result beneath its attempt and carries that digest into the new evidence
chain; an optional caller-supplied prior-result digest must match exactly.

Read-only model commands still need ephemeral files for ordinary validators
such as pytest capture. A first repair tried Codex's beta permission profiles:
an explicit `codex sandbox -P` probe could write attempt-local `TMPDIR` while
denying the checkout, but `codex exec` 0.146.0 did not apply the same profile
selection. Two real xhigh closeout attempts therefore failed before pytest
collection. The runtime must not present that argv shape as proven support.

Instead, semantic target authority and Codex's technical cwd are separated.
For a read-only binding, Codex runs its internal `workspace-write` sandbox over
one runtime-owned attempt-local execution root and `TMPDIR`; the exact target
checkout is supplied as a separate read-only source path outside writable
roots. A real 0.146.0 Luna xhigh probe created a tempfile, received `EROFS` on
direct and symlink-mediated target writes, and received `EXDEV` on hardlink and
rename attempts. The runtime records the execution root, rejects overlap with
the target, keeps network disabled, and retains byte-level final target
manifests. This technical `workspace-write` flag is not repo-mutation authority:
the model realization, binding, task effect, artifacts, and owner review remain
read-only. A fresh owner packet must still prove the full closeout lane.

Every terminal result carries a runtime-owned exact final workspace-manifest
reference. Independent review selects a distinct post-writer manifest as its
admission baseline while preserving the writer baseline under its original
immutable input ID. A repo-mutation writer cannot pass its coder binding or
workspace-write permissions into review: the preparer requires a caller-named,
plan-bound reviewer contract and a same-model/same-effort read-only realization.
Because the final manifest does not exist when the writer begins, the report
may cite it only through the reserved
`runtime:workspace-final-manifest#<anchor>` identity; the controller resolves
that identity after process exit against the exact finalization artifact.
The controller also derives one session-local output schema from the admitted
canonical report schema and pins exact task/incarnation IDs before inference.
An unchanged read-only reviewer rejected only for an identity-field mismatch
may continue the same thread through an explicit prior-result-digest-bound
follow-up; the failed result remains preserved evidence and no automatic retry
or broader failed-session resume is admitted.

## Rationale

A separate process and durable thread make the incarnation observable and
resumable without relying on in-process spawn semantics. Keeping launch apart
from the A2A return reviewer preserves the already accepted boundary that a
reviewed return is an input, not a hidden child-execution command. Exact owner
refs allow model realization and role meaning to evolve independently of the
runtime while still making one invocation reproducible.

Landing is a useful first fit because it has explicit transitions, bounded
artifacts, validators, rollback/re-entry anchors, and a natural independent
review step. Starting read-only keeps quality comparison separate from effect
authority.

## Consequences

- Positive: Luna, Sol, and later models can be compared through one typed,
  persistent, runtime-observed route rather than ambient session behavior.
- Positive: a parent may genuinely yield and re-enter on configured events
  while the exact child thread and continuation obligation remain durable.
- Positive: exact observed validation argv/exit states, byte-aware ignored-path
  drift, produced-artifact and status-selected wake admission, accepted-reviewer
  export gating, semantic source-reference validation, signal-notified
  supervision, and bounded subreaper/TERM/SIGKILL cleanup prevent several
  writer-side false closure classes from becoming accepted runtime results.
- Positive: final-manifest binding and explicit coder-to-reviewer narrowing
  make a bounded workspace-write result independently reviewable without
  granting the reviewer repair authority.
- Positive: distinct mutation and source-evidence scopes let a narrow writer
  cite the owner sources that justify its change without acquiring authority to
  modify those sources, while the reserved final-manifest identity prevents a
  pre-run baseline from masquerading as post-run evidence.
- Positive: the writer's `submit_for_review` decision and the reviewer's
  `return_for_repair` decision are distinct typed handoffs, so a writer cannot
  impersonate the independent review verdict.
- Positive: session-local identity constraints prevent a known task or
  incarnation ID typo from discarding an otherwise complete review, while the
  narrow explicit recovery path preserves the original failure instead of
  silently retrying it.
- Tradeoff: callers must assemble exact plan, incarnation, realization, task,
  role, workspace, schema, and binary coordinates before launch.
- Tradeoff: the initial runtime is source-local and paired to the new SDK
  contract; content-addressed local packaging is available, while landed SDK
  packaging and remote CI remain separate work.
- Tradeoff: parent-death cleanup covers the governed worker lifecycle, but an
  out-of-contract direct `SIGKILL` of the supervisor can bypass its userspace
  cleanup; a stronger guarantee would require a separately admitted compatible
  cgroup containment contract.
- Follow-up: run fixed real-model landing trials, independent review, and an
  `aoa-evals` admission before claiming fit or integrating a center route.

The live candidate-011 writer supplied post-repair Luna transport evidence but
its independent reviewer returned two blockers: permanent 20 Hz procfs work and
two nonexistent report references. That reviewer then exceeded its token
ceiling, so the report remains failed review counterevidence and A2A export is
refused. This correction preserves the accepted boundary while requiring a
fresh immutable writer/reviewer pair after the source repair. It also shows
that the earlier fixed-ceiling design censored the very review it was meant to
measure; subsequent candidates use observe-only metering instead.

Candidate-012 supplied same-packet Luna max and xhigh writer receipts, but no
accepted independent review. The writers surfaced complementary durable-
failure-closeout and evidence-binding gaps; the reviewer confirmed them and
then failed its own exact source-anchor admission. Source v2 state now persists
the task/binding/wake closeout envelope at admission, report evidence admits
only anchored workspace source or stable immutable-input IDs, validation
claims bind exact runtime command IDs, and a canonical non-starting reviewer
preparer forwards all writer immutable inputs plus exact result/report bytes.
These repairs require a fresh immutable pair and do not promote candidate-012.

Candidate-013 supplied the fresh fixed-input Sol max, Luna max, and Luna xhigh
read-only writers plus a separate Luna max reviewer. It confirmed both the
value of the Luna route and further contract gaps: mutable report/A2A evidence,
admission-class overstatement, and the absence of a reviewable post-write
workspace snapshot. The runtime now digest-binds terminal result/report/event
and final-manifest evidence, refuses failed or drifted A2A artifacts, and
supports an explicit workspace-write coder to read-only reviewer transition.
Candidate-013 remains comparison evidence rather than model-fit admission; the
new mutation route still requires its own fixed real-model proof.

The first fixed generated-drift mutation trial supplied Luna max and xhigh
writer evidence plus an independent Luna xhigh review. The max writer and the
reviewer were both rejected because the runtime incorrectly treated narrow
mutation `allowed_paths` as the only admissible source-citation scope. The
xhigh writer repaired the generated index and passed all fixed validations,
but cited the initial dirty workspace manifest for a final-scope claim. The
reviewer independently confirmed both the correct source repair and this
mis-anchor before its own otherwise substantive report hit the same source
scope rejection. These failed receipts remain counterevidence. The resulting
contract separates `source_evidence_paths` from mutation authority and adds the
reserved final-manifest evidence identity; a fresh pair is still required and
no model-fit claim follows from the repair.

The fresh evidence-v2 generated-drift pair then supplied complementary Luna
max and xhigh evidence. Max repaired the exact index but its report invented an
immutable anchor and was rejected. Xhigh repaired the same baseline, passed all
fixed validations, cited the runtime final manifest, and entered independent
review. The distinct xhigh reviewer confirmed the repair but first mistyped its
incarnation ID; the runtime rejected it, preserved that receipt, and an
explicit digest-bound follow-up completed the same reviewer thread under the
new exact identity schema. The resulting A2A-compatible return binds distinct
writer/reviewer threads and exact artifact digests with no parent wake. This is
productive transport and review evidence, not an `aoa-evals` verdict, owner
acceptance, landing completion, or general Luna-fit claim.

The installed-runtime workspace-write reproduction then exercised the full
machine-local contour rather than a source-worktree launcher. Luna xhigh ran in
a separately addressable workspace-write session, repaired only the authorized
generated decision index, passed the fixed validators, and returned
`review_required`. A distinct external read-only Luna xhigh session changed no
path, matched the post-writer manifest, and returned `completed/proceed`. The
reviewed A2A return binds exact summon-request v4, writer result, reviewer
result, report, and final-manifest digests. The combined observation counted
2,616,871 input tokens, 2,372,096 cached input tokens, 30,058 output tokens,
611.381005 active seconds, 104 commands, and 834,221 output bytes without an
execution budget. This closes the bounded installed process/session/reviewed-
return mechanism question. It does not establish Luna net benefit, general
landing fit, production admission, owner acceptance, or effect authority.

## Source surfaces

The first live ambiguity-stop L2 study tested the parent lifecycle itself. Its
first xhigh child selected the safe escalation direction but emitted an invalid
bare numeric source anchor. Runtime retained the failed child result, selected
`result.failed/stop`, and left the yielded parent at one turn. A new immutable
v2 packet pinned the corrected line-anchor contract and runtime-controller
source. Luna xhigh returned a schema-valid `authority_blocked` result with
`run.authority_required`; the runtime admitted exactly that event and resumed
the same parent Sol thread after an inference-free wait. The second parent turn
returned `request_human_authority`. This closes the bounded product-surface L2
transport question while preserving the failed first run as counterevidence.
It does not supply an `aoa-evals` verdict, Luna admission, accepted outcome,
realized USD cost, or center-integration authority.

- `mechanics/governed-execution/parts/external-codex-agent/`
- `scripts/aoa-external-codex-agent`
- `mechanics/governed-execution/parts/agent-os-adapter/`
- `mechanics/governed-execution/PARTS.md`
- `mechanics/governed-execution/PROVENANCE.md`

## Follow-up route

Keep the installed lane explicitly nonproduction and externally effect-gated.
Route the source-local and installed-runtime comparison receipts to
`aoa-evals`; expand to held-out obligations and measure review/rework cost
before any Luna-fit or domain-route admission. Land and remotely validate the
SDK/runtime source before production activation. Treat center integration,
persistent-role wake policy, and every external effect as separate
owner-reviewed decisions.
