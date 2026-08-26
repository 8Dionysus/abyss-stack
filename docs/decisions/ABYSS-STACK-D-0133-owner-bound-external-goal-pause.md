# Owner-Bound External Goal Pause

- Decision ID: ABYSS-STACK-D-0133
- Status: superseded
- Superseded by: `ABYSS-STACK-D-0138-native-goal-pause-request-and-post-read-proof.md`
- Date: 2026-08-22
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`

## Index Metadata

- Original date: 2026-08-22
- Surface classes: public-contract, lifecycle, source/runtime boundary
- Stack lanes: governed-execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: Goal identity binding, lifecycle transition, evidence separation
- Posture: accepted runtime rationale

## Context

The external Codex return contour could wake a supplied paused Goal and deliver
a handoff, but the master-side active-to-paused transition had no supported,
inspectable runtime path. The historical workaround depended on a task-specific
Goal, Kitty TTY input, and GDB, which could not preserve unrelated actors or
prove the lifecycle transition through the owning control surface.

## Options considered

- Continue using task-local TTY/GDB injection to request `/goal pause`.
- Add a task-specific helper that selects the current master Goal or process.
- Extend the installed, model-neutral Codex transport adapter with a separate
  owner-bound Goal pause action and receipt.

## Decision

Use the third route, with a fail-closed protocol capability gate.
`aoa-external-codex-return pause` accepts a separate pause-owner binding and
receipt path, reads the exact Goal through the current local Codex app-server,
requires `active`, and can call only `thread/goal/set(status=paused)` through an
`atomic_goal_transition` adapter method that supplies a server-supported
compare-and-set/version proof. The
installed public `ThreadGoalSetParams` method has no such precondition, so the
canonical adapter currently refuses to mutate or certify a fresh
`active_to_paused` transition. A future protocol adapter must return the typed
`abyss_stack_external_codex_atomic_goal_transition_v1` proof, which the receipt
binds to the active precondition, exact request, and Goal response. The receipt
is distinct from return/wake delivery and holder closure, and keeps owner
acceptance and semantic acceptance separate.

## Rationale

The owner artifact supplies the Goal/thread coordinates, so the runtime does
not select a task, process, terminal, workspace, model, or hardcoded Goal. The
app-server is the current replaceable transport adapter; the lifecycle action
is inspectable and uses no TTY injection, PID signaling, GDB, keystrokes, turn
delivery, or holder close. Reserving and digest-binding the receipt preserves
recovery evidence without claiming that a runtime transition is semantic or
human acceptance.

## Consequences

- Positive: any master session with a protocol-capable adapter can request an
  exact active-to-paused Goal transition through a stable installed route.
- Positive: pause, wake delivery, holder closure, semantic re-entry, and owner
  acceptance remain separately reviewable claims.
- Tradeoff: Codex app-server is the only transport in this slice; another
  runtime needs its own owner-specific adapter.
- Recovery: the receipt reservation records the active precondition before the
  lifecycle mutation. If a typed atomic transition proof was durably persisted
  but the response or receipt publication was lost, a retry can reconcile the
  exact paused Goal through a read-only `thread/goal/get` and never repeats
  `thread/goal/set`. A lost response without that proof is not recoverable as
  an exact pause receipt.
- Unchanged: no actor is stopped or restarted by pause, and no model, role,
  eval, sibling-owner, host exposure, secret, or service authority is added.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_return.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-pause-owner.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-pause-receipt.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_return.py`

## Follow-up route

The current master owner supplies the exact pause-owner artifact and, once a
protocol-capable app-server exists, proves the live Goal transition. The
current public app-server capability gap is a runtime blocker, not a source
acceptance or live-canary result. The existing external return leaf remains
the later wake and holder-close route; a future non-Codex transport owner may
add a parallel adapter without changing the holder contract.
