# Native Goal Pause Request And Post-Read Proof

- Decision ID: ABYSS-STACK-D-0138
- Status: accepted
- Date: 2026-08-26
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`
- Supersedes: `ABYSS-STACK-D-0133`

## Index Metadata

- Original date: 2026-08-26
- Surface classes: public-contract, lifecycle, source/runtime boundary
- Stack lanes: governed-execution, external Codex runtime, validation
- Mechanic parents: `mechanics/governed-execution`
- Guard families: Goal identity binding, lifecycle transition, evidence separation
- Posture: accepted repair rationale

## Context

The earlier owner-bound pause decision required a server-side compare-and-set or
version proof before issuing `thread/goal/set`. The current Codex 0.149.1
`ThreadGoalSetParams` surface exposes no such field, so the installed adapter
refused a valid owner-authorized pause before mutation and could not serve a
fresh active-to-paused canary.

## Options considered

- Keep the unsupported CAS/version gate and permanently reject the current
  public Goal mutation surface.
- Reintroduce task-local TTY, keystroke, or debugger injection for this one
  pause operation.
- Issue the native Goal set once under the exact owner binding, persist request
  evidence, and certify the resulting state with a bounded fresh Goal read.

## Decision

Use the native `thread/goal/set` request exactly once after reading the exact
owner-bound Goal and requiring the expected current state. Bind the request
identity, owner thread, and returned response when available; then perform a
bounded `thread/goal/get` and require the requested resulting state. Persist a
versioned observational proof containing the active precondition, exact
request, optional mutation response digest, and post-read digest. If the
response is lost after durable dispatch, reconcile only from the dispatch
marker and fresh post-read; never issue a second lifecycle set. Historical
atomic proof records remain readable only for migration/replay and do not
authorize a new mutation.

Pause evidence remains separate from transport ambiguity, wake delivery,
semantic acceptance, owner acceptance, holder closure, and Goal completion.
The completed pause receipt retains the raw post-read response as well as its
safe summary and digest; proof-recorded recovery reuses those stored bytes,
while a fresh read is only an owner-identity and current-state check. Receipt
replay therefore tolerates mutable app-server metadata without rewriting the
historical transition evidence. The legacy pause entrypoint remains a
mutating compatibility path for new reservations, while replay of a completed
receipt is read-only.

## Rationale

This matches the actual public protocol instead of requiring an unavailable
feature, while retaining exact owner/thread binding, durable recovery evidence,
and fail-closed behavior when dispatch or post-read evidence is incomplete.
The runtime makes no unsupported server-side causality claim and does not widen
the operation into a task-specific actor, model, terminal, PID, or debugger
route.

## Consequences

- Positive: a current Codex app-server can serve the owner-authorized pause
  contour and produce a truthful observable proof.
- Positive: a lost response can be reconciled without replaying the mutation
  when the durable dispatch marker proves that the exact request was issued.
- Tradeoff: without a protocol CAS/version field, a receipt proves the bound
  request and post-read observation, not server-side compare-and-set causality.
- Follow-up: live pause, root wake, holder closure, owner acceptance, and
  semantic continuation still require their own current evidence.
- Unchanged: no actor is stopped or restarted by pause, and no model, role,
  eval, sibling-owner, host exposure, secret, or service authority is added.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_return.py`
- `mechanics/governed-execution/parts/external-codex-agent/goal_lifecycle_adapter.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-pause-reservation.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-goal-lifecycle-attempt.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_return.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_goal_lifecycle_adapter.py`

## Follow-up route

Use the owner release/install route for source validation, admission,
activation, and rollback. The installed canary must separately read the Terra
Goal before and after the one native set; its receipt is not a root wake or
holder-closure receipt. Revisit this decision only if the Codex protocol gains
an explicitly supported stronger transition primitive.
