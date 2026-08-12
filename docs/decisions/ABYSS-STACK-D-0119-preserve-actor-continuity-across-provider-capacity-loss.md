# Preserve Actor Continuity Across Provider Capacity Loss

- Decision ID: ABYSS-STACK-D-0119
- Status: accepted
- Date: 2026-08-12
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-12
- Surface classes: runtime boundary, actor continuity, provider capacity
- Stack lanes: runtime, evidence, validation
- Mechanic parents: governed-execution
- Guard families: exact-thread resume, evidence closure, bounded authority
- Posture: accepted pre-turn capacity recovery; no generic retry

## Context

The first real role-first stats and memo duties each reached a separately
addressable Luna xhigh Codex thread and an unchanged runtime-owned projection.
ChatGPT then returned its structured usage-limit error before either actor
completed a turn, issued a command, changed a path, or emitted token usage.

The runtime preserved both exact `error` and `turn.failed` protocol records,
the thread, manifests, delta, result, and owner inputs. It nevertheless reduced
the terminal state to `codex_process_failed`. Failed-session admission
supported only reviewer identity repair and writer report repair, so an
external capacity interruption destroyed practical role continuity despite
the evidence showing that the obligation itself had not begun to move.

## Options considered

- Start a new incarnation and abandon the existing role/thread whenever
  provider capacity returns.
- Treat every `codex_process_failed` result as resumable.
- Introduce a provider-capacity route admitted only from an exact structured
  pre-turn failure and an intact original authority/evidence contour.

## Decision

Classify the exact Codex ChatGPT usage-limit terminal pair as
`provider_capacity_unavailable`. Admit an explicit `capacity_recovery`
same-thread continuation only when all of the following remain true:

- the prior result binds the exact per-attempt raw Codex JSONL artifact;
- that artifact ends with a top-level provider `error` immediately followed by
  `turn.failed` carrying the identical bounded usage-limit message;
- the result records zero completed turns, zero token observations, no
  commands, and no changed paths;
- source and actor manifests match, and actor final-manifest/delta evidence is
  present;
- the request binds the exact session, thread, event cursor, and prior result
  digest;
- the general prior-result evidence closure verifies before another attempt.

For already-preserved releases, a legacy `codex_process_failed` result may use
this route only when the exact result-bound raw event artifact independently
proves the same provider-capacity pair. An arbitrary process failure, stderr
message, model-authored text, loose substring, changed workspace, or drifted
evidence cannot qualify. Recovery is caller-triggered after capacity returns;
the runtime does not poll or retry automatically.

## Rationale

Provider capacity is a property of the current physical incarnation service,
not evidence that the actor's role or responsibility disappeared. Preserving
the same thread retains useful identity and context while the exact owner role,
task, model, projection, tools, effects, and authority remain unchanged.

The pre-turn and zero-effect requirements make this first route deliberately
narrow. They solve the witnessed stats/memo failure without converting a
generic execution error into a retry mechanism. Structured event and result
digests keep the decision grounded in runtime-owned evidence rather than in
caller prose.

## Consequences

- Positive: a real obligation can survive temporary ChatGPT capacity loss
  without being re-created as a disposable worker.
- Positive: historical generic results from the witnessed failure remain
  recoverable when their exact raw evidence still verifies.
- Positive: the route is role- and model-neutral; Luna is the first witness,
  not an architectural dependency.
- Tradeoff: capacity loss after commands, changes, or completed turns remains
  outside this initial route and needs separate evidence before expansion.
- Negative: a changed provider error shape fails closed until the owner
  deliberately admits that new structured contract.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-resume.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/SUSPENSION.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

Land and activate one clean content-addressed runtime release. After ChatGPT
capacity returns, resume the preserved stats and memo threads through exact
`capacity_recovery` requests, complete their original duties, and route their
returns through independent review. Broader mid-turn capacity recovery remains
future work unless real evidence justifies it.
