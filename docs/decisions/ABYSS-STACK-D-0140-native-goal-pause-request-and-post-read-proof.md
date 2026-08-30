# Native Goal Pause Request And Post-Read Proof

- Decision ID: ABYSS-STACK-D-0140
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

The qualified owner identity and accepted idempotency key also own a protected
anchor in persistent owner state for the first durable attempt path. The
advisory lock remains in volatile runtime state, but reboot or runtime-directory
replacement cannot erase the owner anchor. Alternate caller-selected receipt
paths resolve that anchor instead of creating fresh lifecycle state; if another
accepted transition later restores the original Goal state, a retry of the old
idempotency key still finds the completed attempt and refuses a second mutation.
When the first execution only observes an already-desired state, it records a
durable `read_only_recorded` attempt at the same anchor. A later reversal cannot
turn that no-mutation completion into permission to issue a delayed set. The
anchor remains authoritative if a caller later cleans the referenced sidecar:
the missing target is terminal and must not be recreated. The v2 anchor records
whether a valid attempt has actually started; endpoint discovery or RPC setup
failure before that point leaves an explicit unstarted anchor that a retry may
reuse. A replayed read-only
receipt is accepted only when its historical response bytes, summaries, and
digests match the anchored `read_only_recorded` observation.
Dynamic endpoint rebinding may change the fresh transport coordinate but does
not rewrite the attempt's historical endpoint evidence.
The CLI reasserts the original request, decision, and owner bytes immediately
before dispatch and after receipt publication. The legacy pause compatibility route lacks the typed
idempotency artifact, so it serializes by qualified Goal identity across
receipt paths, reasserts its owner snapshot before mutation and after proof
persistence, and fails closed rather than issuing a concurrent duplicate or
publishing a completed receipt against rewritten owner authority.

Pause evidence remains separate from transport ambiguity, wake delivery,
semantic acceptance, owner acceptance, holder closure, and Goal completion.
The completed pause receipt retains the raw mutation response and raw post-read
response as well as their safe summaries and digests; proof-recorded recovery
reuses stored post-read bytes, while a fresh read is only an owner-identity and
current-state check. Receipt
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
- Positive: alternate receipt paths, endpoint rebinding, later state reversal,
  volatile runtime-directory loss, and concurrent legacy pause callers cannot
  cause a duplicate native set for the same admitted contour.
- Positive: read-only completion remains idempotent after a later state
  reversal even if its sidecar is later removed, its receipts remain bound to
  the recorded observation, and legacy owner drift is detected at the
  mutation/proof boundary.
- Positive: a transport failure before any attempt exists does not permanently
  consume the accepted idempotency key.
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
