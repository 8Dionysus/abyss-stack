# Preserve Writer Role Continuity for Report Repair

- Decision ID: ABYSS-STACK-D-0115
- Status: accepted
- Date: 2026-08-11
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-11
- Surface classes: runtime boundary, actor continuity, A2A return
- Stack lanes: runtime, evidence, validation
- Mechanic parents: governed-execution
- Guard families: exact-thread resume, evidence closure, bounded authority
- Posture: accepted same-role report recovery; no authority widening

## Context

The first owner-contour Luna landing writer completed its bounded workspace
work, left the owner source unchanged, produced only allowed actor artifacts,
and returned the intended transition and validation facts. Runtime admission
nevertheless rejected the terminal return because its model-authored runtime
evidence anchors did not name literal keys or paths in the final actor
manifest.

The runtime preserved the complete failed result, final actor manifest, delta,
events, and Codex thread. It could continue a failed read-only reviewer after
one identity typo, but it classified every failed writer as nonresumable. The
only operational route was therefore to discard a valid role continuum and
repeat the expensive obligation from a new session.

## Options considered

- Start a new writer incarnation and repeat the whole obligation whenever its
  terminal report is rejected.
- Convert the failed writer to a new read-only reviewer-style recovery role.
- Continue the exact writer role and thread only when its preserved terminal
  evidence proves that the failure belongs to model-report admission and that
  the original authority contour remained intact.

## Decision

Admit an explicit `bounded_repair` continuation for a failed
`bounded_execution`/`repo_mutation` actor when all of the following hold:

- the failure code is in the `model_report_*` admission family;
- the owner source manifest still matches;
- the terminal result carries actor final-manifest and delta references;
- every observed changed path remains inside the task's original
  `allowed_paths`;
- the request binds the exact session, thread, event cursor, and prior result
  digest;
- the prior result and its referenced evidence closure verify before a new
  attempt starts.

The continuation retains the same role, task, projection, model thread, and
authority envelope. It does not gain read-only status, new paths, new effects,
or external authority. Runtime records a distinct
`external_agent.failed_writer_report_resume_admitted` event. The existing
read-only reviewer identity-repair route remains separate.

## Rationale

Role continuity is part of the actor contract: a report-format defect after
safe work should be repairable by the responsibility holder that already has
the relevant context. Requiring evidence-complete safe closeout distinguishes
that situation from authority drift or an unobservable workspace. Keeping the
original envelope lets the capable actor correct its own return without
pretending that it has become another role or encoding a one-off Luna rule.

The `model_report_*` family is appropriate because those failures arise while
admitting the actor's structured return. Unsafe source or projection effects
are independently observed and produce authority-blocked or non-report runtime
failure evidence rather than qualifying silently through this route.

## Consequences

- Positive: a specialized writer can repair its A2A return in the same Codex
  thread without repeating already completed work.
- Positive: the recovery remains model-neutral and role-first; Luna is the
  first real witness, not an architectural dependency.
- Positive: prior failed bytes and their evidence closure remain available as
  counterevidence in the continued result.
- Tradeoff: the continued writer still has its original repo-mutation envelope;
  correct prompting and the existing effect observer remain relevant.
- Negative: failures without exact source, manifest, delta, path, result, and
  thread proof remain nonresumable through this route.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

Rerun the preserved Luna landing writer through this exact recovery route,
then pass an accepted writer result into the independent review/A2A return
lane. `aoa-agents` continues to own role and responsibility, `aoa-models` owns
realization fit, `aoa-sdk` owns the continuation binding, and `abyss-stack`
owns this physical runtime proof.
