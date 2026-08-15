# Visible Holder Terminal Lifecycle Identity

- Decision ID: ABYSS-STACK-D-0124
- Status: accepted
- Date: 2026-08-15
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`

## Index Metadata

- Original date: 2026-08-15
- Surface classes: runtime lifecycle, actor identity, source/runtime boundary
- Stack lanes: governed execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: exact process identity, handoff delivery, terminal closeout
- Posture: accepted responsibility-holder lifecycle boundary

## Context

The operator-visible external Codex route has two different process roles: the
responsibility holder that owns the return, and any nested proof or runtime
actor used to produce evidence. The previous host closer selected fields named
`runtime.actor_*` from a handoff. That could close a completed proof actor while
leaving the actual holder Kitty alive, even though wake delivery itself was
successful.

## Options considered

- Continue selecting a process by worktree, manifest, model, and executable
  fields from the generic runtime actor projection.
- Keep the closer as a private host-only process matcher and add more heuristics
  for visible terminals.
- Have the visible launcher write a non-replacing holder receipt before its
  direct `exec`, then let the installed owner runtime close only that exact
  PID/start-ticks/argv and direct Kitty parent after a delivered wake receipt.

## Decision

Use the third route. `launch --holder-receipt` is valid only for the direct
operator-visible `exec` route and records the actual responsibility-holder
process, its direct Kitty parent, exact argv, and executable/manifest digests.
The installed `close` operation requires a wake receipt that proves the exact
handoff was delivered, revalidates the recorded process identity, sends `TERM`
to that one Kitty, and emits a closure receipt only after the holder and Kitty
are gone. A nested proof actor's runtime result or process identity is never a
holder-close target.

## Rationale

The launcher is the only source-owned point that sees the operator-visible
process immediately before `exec`, so it can preserve the PID identity without
guessing from later process scans. Start ticks and exact argv prevent PID reuse
or a same-model/worktree process from satisfying the close route. Requiring the
already-generated wake receipt keeps terminal disappearance after confirmed
return delivery, while rejecting detached Kitty receipt binding avoids an
unobservable child identity.

## Consequences

- Positive: responsibility-holder and proof-actor lifecycle evidence remain
  distinct and auditable.
- Positive: an ambiguous, reused, drifted, or undelivered target fails closed.
- Tradeoff: this first route requires a direct Kitty parent and does not claim a
  generic detached-terminal lifecycle.
- Unchanged: no host exposure, secret, storage, recurrence, service, model-fit,
  owner acceptance, or semantic proof authority is added.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-holder-terminal-receipt.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-holder-terminal-closure.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

The owner release gate and a live visible trial must verify the installed
receipt/close route, exact master wake delivery, holder-only terminal closure,
and preservation of unrelated terminals before the residual duty is accepted
as complete.
