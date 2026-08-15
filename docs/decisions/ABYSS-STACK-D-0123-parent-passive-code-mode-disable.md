# Parent Passive Turns Disable Code Mode

- Decision ID: ABYSS-STACK-D-0123
- Status: proposed
- Date: 2026-08-15
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`

## Index Metadata

- Original date: 2026-08-15
- Surface classes: external actor runtime, parent re-entry, security
- Stack lanes: governed execution, validation, review
- Mechanic parents: governed-execution
- Guard families: passive parent turn, tool-event rejection, process containment
- Posture: proposed runtime invariant pending independent review

## Context

Parent yield and re-entry turns must not use tools or external effects. The
runtime already rejects every non-passive Codex item after launch, but current
Codex emits a diagnostic `item.error` when the `code_mode_host` feature is
explicitly disabled. That diagnostic is itself correctly rejected as a
non-passive item, so a valid structured parent yield cannot reach the durable
waiting state.

## Options considered

- Keep disabling `code_mode_host`. This preserves the literal host-disable
  wording but makes every current parent turn fail closed before its typed
  result is admitted.
- Do not disable code mode. This avoids the startup diagnostic but leaves an
  unnecessary tool-bearing feature available to the model.
- Disable the `code_mode` feature, leave the host flag untouched, and retain
  the passive-item allowlist. This suppresses code-mode use while preserving
  the fail-closed boundary for any unexpected tool item.

## Decision

Parent Codex commands disable `code_mode` rather than `code_mode_host`.
`shell_tool` and all other tool-bearing features remain disabled, and the
parent event loader continues to admit only `agent_message` and `reasoning`
items. Any other item remains a terminal runtime failure.

## Rationale

The current CLI's host-disable diagnostic is not useful evidence of a model
tool attempt and prevents the owner-defined passive yield contract from
working. Disabling the feature addresses the capability directly, while the
existing event allowlist protects against future CLI or model behavior that
emits a tool item. This keeps the parent lifecycle explicit, bounded, and
recoverable without treating a proxy-green turn as proof.

## Consequences

- Positive: current Codex 0.147.0 can produce a passive structured yield and
  re-entry result that the runtime can bind to its event stream.
- Positive: unexpected tool events remain fail-closed and independently
  testable.
- Tradeoff: the command does not express a separate host-disable flag; the
  passive event boundary is therefore part of the security contract and must
  not be weakened.
- Follow-up: reprove parent yield, authority wake, same-thread re-entry, and
  original master wake on the merged release.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `CHANGELOG.md`

## Follow-up route

The external Codex owner reviewer should inspect the exact command diff and
passive-event regression before artifact staging and activation. Runtime
trust, host cutover, and master acceptance remain separate checks.
