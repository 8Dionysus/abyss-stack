# Bind Terminal Validation Suite After Command-Sandbox Settlement

- Decision ID: ABYSS-STACK-D-0116
- Status: accepted
- Date: 2026-08-11
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-11
- Surface classes: runtime boundary, validation evidence, actor projection
- Stack lanes: runtime, evidence, validation
- Mechanic parents: governed-execution
- Guard families: fixed validation, full manifest, fail closed
- Posture: accepted terminal-suite binding; no arbitrary command relaxation

## Context

The resumed Luna landing writer returned corrected runtime evidence anchors and
ran all six exact fixed validations in task order. The first Git validation and
the following JSON validation were observed against one full actor-manifest
digest. During the third exact command, delayed command-sandbox cleanup settled
and the actor projection returned to the same manifest that had been preserved
from the prior attempt. The remaining four validation receipts and terminal
manifest all bound that preserved digest; owner source and cumulative actor
delta remained unchanged.

The runtime nevertheless rejected the return because it required every
per-command full-manifest digest to equal the terminal digest. Retrying an
inventory read cannot solve this case: both observations were individually
valid, while controller-visible transient command state settled between them.
Adding sleeps or asking a capable actor to guess runtime teardown timing would
move a transport responsibility into role prompting.

## Options considered

- Require every actor to delay and repeat validations until all immediate
  full-manifest receipts happen to match.
- Drop per-command workspace binding and trust only argv and exit status.
- Keep immediate full-manifest receipts, retain the ordinary all-equal rule,
  and add one narrow alternative for the exact complete validation suite when
  it is the terminal command suffix and ends on the final manifest.

## Decision

Each fixed validation receipt continues to record the complete actor-manifest
digest observed at `item.completed`. Report admission first applies the existing
rule: every selected last execution for every task-declared validation must
match the final manifest.

When one or more receipts differ, admission succeeds only if:

- the selected last executions form the complete task-declared validation
  sequence in exact order;
- those executions are the terminal completed-command suffix of the current
  attempt, with no later model command;
- the last fixed validation receipt matches the final full actor manifest;
- all existing exact argv, descriptor-bound cwd, wrapper argv, exit-status,
  source, path, effect, and final-manifest checks still pass.

An incomplete, reordered, interleaved, or nonterminal suite remains
`model_report_validation_workspace_unbound`. A mutation after a single
validation receipt also remains rejected because its last receipt does not
bind the final manifest.

## Rationale

The exact terminal suffix proves that the actor finished with the owner-fixed
validation procedure rather than validating early and then changing the
workspace. Requiring its last command to bind the final complete manifest
anchors the return after transient command-sandbox state has settled. Retaining
every immediate digest keeps the discrepancy auditable rather than rewriting
history.

This is narrower than time-based stabilization. The controller does not sleep
while Codex may start another command, guess a teardown duration, or relabel an
arbitrary command as validation. It also preserves initiative: the actor runs
the declared procedure normally, while runtime owns the semantics of its
transport observations.

## Consequences

- Positive: real exact validation suites can survive transient sandbox cleanup
  without prompting delays or duplicated work.
- Positive: later commands and post-validation mutations remain fail-closed.
- Positive: every immediate manifest remains durable counterevidence, including
  receipts that differ from the terminal manifest.
- Tradeoff: an owner-fixed later validation command may be the point at which
  transient controller state settles; the accepted proof is therefore the
  terminal suite as a whole, not a claim that every intermediate private Git
  byte was identical.
- Negative: a nonterminal validation sequence must still be rerun after the
  actor's last command.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

Resume the preserved Luna landing thread again from its second failed result,
require cumulative artifact paths in the corrected return, and carry an
accepted writer result into the separate independent review/A2A lane. A future
runtime that can observe command-sandbox teardown directly may supersede this
terminal-suite fallback without changing role or owner contracts.
