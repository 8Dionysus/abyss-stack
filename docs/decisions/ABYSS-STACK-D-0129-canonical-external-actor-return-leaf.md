# Canonical External Actor Return Leaf

- Decision ID: ABYSS-STACK-D-0129
- Status: accepted
- Date: 2026-08-21
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`

## Index Metadata

- Original date: 2026-08-21
- Surface classes: public-contract, lifecycle, source/runtime boundary
- Stack lanes: governed-execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: return-owner binding, handoff delivery, holder closure
- Posture: accepted runtime rationale

## Context

External Codex holders were returned through task-local scripts that selected a
particular Goal, thread, disposition, and task-root path. Reusing those scripts
made delivery drift and left exact visible holders open after an unsuccessful
wake. The runtime already had typed join, wake authorization, and exact close
primitives, but no installed owner-neutral leaf composed them with a factual
Codex Goal/session delivery receipt.

## Options considered

- Keep task-local wake scripts and require each caller to maintain its own
  app-server protocol and close ordering.
- Add a task-specific helper to the installed runtime for the current Goal.
- Publish one runtime-owned return leaf that accepts owner, handoff, transport,
  and holder identities as validated inputs and composes the existing typed
  lifecycle primitives.

## Decision

Use the third route. `aoa-external-codex-return return` accepts an explicit
return-owner binding and exact handoff/holder/receipt paths. For the Codex
transport it resolves an explicit or current-local app-server UNIX socket,
activates the supplied Goal, steers an active turn or starts a new turn, and
records `abyss_stack_external_codex_return_receipt_v1`. It then reuses
`authorize-close` and `close` for the exact bound holder. A detached mode uses
the same operation in a new session and leaves durable result evidence.

## Rationale

The owner binding carries all episode-specific coordinates, so the reusable
runtime does not select a task, rollout, PR, disposition, or workspace by
constant. Delivery, owner acceptance, semantic re-entry, and terminal
disappearance remain separate claims. Reusing the existing closer preserves
its PID/start-ticks, Kitty dedication, reservation, and mismatch guards rather
than creating a second signal protocol.

## Consequences

- Positive: `aoa-agents/aoa-summon` has one stable external-return leaf and
  schema surface to adopt.
- Positive: active and paused Codex sessions share one receipt-bearing route,
  and a completed return receipt can resume authorization/closure without
  repeating delivery.
- Tradeoff: Codex app-server is the only transport in this slice; other
  runtimes must provide a future owner-specific adapter.
- Unchanged: no model selection, role meaning, owner acceptance, host exposure,
  service enablement, or sibling-repository authority is added.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_return.py`
- `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/install_external_codex_runtime.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-return-owner.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-return-receipt.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`

## Follow-up route

`aoa-agents/aoa-summon` should consume the installed return leaf by passing
owner-selected identities and should keep owner acceptance and semantic
continuation outside the runtime receipt. A future transport owner may add a
typed adapter without changing the holder close contract.
