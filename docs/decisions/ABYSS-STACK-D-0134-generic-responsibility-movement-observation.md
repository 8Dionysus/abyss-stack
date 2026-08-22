# Generic Responsibility-Movement Observation

- Decision ID: ABYSS-STACK-D-0134
- Status: accepted
- Date: 2026-08-22
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`

## Index Metadata

- Original date: 2026-08-22
- Surface classes: public-contract, lifecycle, source/runtime boundary
- Stack lanes: governed-execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: lifecycle transition, bounded observation, typed wake
- Posture: accepted runtime rationale

## Context

An external holder can remain alive while the responsibility transition it
accepted never advances. The prior operational pressure included a real
`cannot connect to Codex app-server` return failure while the master Goal
remained paused. A hook-screen check would cover one visible cause, but would
not provide a model-neutral detector for startup gates, input waits, transport
stalls, crashed turns, or silent execution loss.

## Options considered

- Match a hook or terminal screen and treat the match as stasis.
- Poll holder processes continuously and infer progress from liveness.
- Observe one bound transition snapshot, account for its cost, and emit a
  typed review wake when the transition is overdue and absent.

## Decision

Use the third route. The runtime accepts a compiled obligation, exact holder
and return-owner identity, handoff, lifecycle transition, timestamp, cost
budget, and immutable stop line. A one-shot observation classifies only
`progressing`, `not_due`, `cost_deferred`, or `stasis`. Only a matching
model-neutral lifecycle transition is positive movement evidence. A due
missing transition emits a typed stasis event and a review-only wake bound to
the same return owner and canonical return transport.

## Rationale

The transition requirement preserves causal meaning across different actor
causes and does not promote process existence, unchanged files, or UI state to
responsibility progress. The bounded one-shot shape avoids a hidden polling
daemon and makes cost visible. The typed wake preserves asynchronous owner
review while keeping transport delivery, holder closure, semantic re-entry,
Goal acceptance, and the external canary as separate claims.

## Consequences

- Positive: the real app-server connectivity failure can be represented as
  transport evidence contributing to a missing-transition diagnosis without
  being confused with a hook-screen match.
- Positive: automatic kill/restart, domain-failure declaration, Goal
  acceptance, and unrelated-actor mutation remain outside the observer.
- Tradeoff: transition deadlines and first healthy timings must be learned
  from observed runs; the runtime does not invent universal timeout constants.
- Follow-up: the return owner must deliver the bound wake through the current
  app-server resolver and separately prove holder closure and Goal re-entry.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_responsibility_movement.py`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_return.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-responsibility-observation.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-responsibility-movement.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_responsibility_movement.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`

## Follow-up route

The canonical master return owner supplies current app-server evidence and
performs the exact final pause-and-return canary when the app-server exposes an
`atomic_goal_transition` method with a server-supported atomic Goal transition
proof. The current public
`ThreadGoalSetParams` method does not, so a live fresh pause is fail-closed and
must not be represented as a canary result. Preserve the separate host
trust-admission blocker and keep external-canary and Goal acceptance claims
outside this runtime result.
