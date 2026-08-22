# Owner-Bound External Goal Pause

- Decision ID: ABYSS-STACK-D-0133
- Status: accepted
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

Use the third route. `aoa-external-codex-return pause` accepts a separate
pause-owner binding and receipt path, reads the exact Goal through the current
local Codex app-server, requires `active`, calls only
`thread/goal/set(status=paused)`, and validates the returned `paused` Goal. Its
receipt is distinct from return/wake delivery and holder closure, and keeps
owner acceptance and semantic acceptance separate.

## Rationale

The owner artifact supplies the Goal/thread coordinates, so the runtime does
not select a task, process, terminal, workspace, model, or hardcoded Goal. The
app-server is the current replaceable transport adapter; the lifecycle action
is inspectable and uses no TTY injection, PID signaling, GDB, keystrokes, turn
delivery, or holder close. Reserving and digest-binding the receipt preserves
recovery evidence without claiming that a runtime transition is semantic or
human acceptance.

## Consequences

- Positive: any master session can request an exact active-to-paused Goal
  transition through a stable installed route.
- Positive: pause, wake delivery, holder closure, semantic re-entry, and owner
  acceptance remain separately reviewable claims.
- Tradeoff: Codex app-server is the only transport in this slice; another
  runtime needs its own owner-specific adapter.
- Unchanged: no actor is stopped or restarted by pause, and no model, role,
  eval, sibling-owner, host exposure, secret, or service authority is added.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_return.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-pause-owner.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-pause-receipt.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_return.py`

## Follow-up route

The current master owner supplies the exact pause-owner artifact and proves
the live Goal transition. The existing external return leaf remains the later
wake and holder-close route; a future non-Codex transport owner may add a
parallel adapter without changing the holder contract.
