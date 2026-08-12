# Admit Role-First Owner Reviewers to A2A Return

- Decision ID: ABYSS-STACK-D-0118
- Status: accepted
- Date: 2026-08-12
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-12
- Surface classes: runtime boundary, actor admission, independent review, A2A return
- Stack lanes: source, runtime, review
- Mechanic parents: governed-execution
- Guard families: owner provenance, immutable inputs, exact binding, independent review
- Posture: accepted role-first owner-contour reviewer and responsibility return

## Context

Decision D-0113 carried an owner-contour writer through a separately addressed
reviewer by retaining the reviewer as a `transport_study_fixture`. That was a
useful compatibility step while reviewer construction remained inside the
landing-study preparer, but it no longer describes a reviewer that has its own
obligation, mandate, role resolution, model-fit selection, SDK incarnation,
owner execution request, task-local DAG node, and responsibility transfer.

The role-first compiler in `aoa-agents` can now form that independently owned
review obligation without launching it. A real eval-selection writer and a
separate read-only reviewer then demonstrated that both incarnations can be
admitted as `owner_contour`, retain distinct Codex threads, and return one
reviewed A2A result. The runtime needed a model-neutral admission path for that
stronger relationship without widening either actor or removing the historical
compatibility lane.

## Options considered

- Keep all reviewers as transport-study fixtures even after they receive a
  complete owner responsibility chain.
- Route every domain reviewer through the landing-specific preparer and rename
  its outputs after execution.
- Admit an exact `owner_contour` writer/reviewer pair through a dedicated
  evidence-closed A2A path while retaining the historical fixture paths.

## Decision

The A2A exporter accepts an `owner_contour` writer with an `owner_contour`
reviewer only through a dedicated role-first branch. The branch requires:

- terminal failure-free runtime results with reports whose task, incarnation,
  status, and decision agree;
- distinct sessions, incarnations, and Codex threads;
- reviewer posture `independent_review`, read-only sandbox, no external
  effects, and zero actor delta;
- exact immutable reviewer inputs for the writer task, result, report, and
  every writer-produced artifact named by the report;
- exact owner and parent relationships, including the reviewed writer result
  path and the reviewer request parented to the writer task;
- exact SDK v4 summon requests and request-schema bytes for both incarnations;
- final revalidation of both durable states and every exported artifact while
  writer and reviewer locks are held through atomic publication.

The payload records `review_binding_mode` as
`owner_contour_immutable_evidence`. A completed `proceed` review returns a
completed child task; a review-required `return_for_repair` returns the exact
failed repair handoff. Neither outcome claims domain-owner acceptance, eval
proof, model fit, landing, publication, or a new authority grant.

Historical transport-study and mixed owner-writer/fixture-reviewer routes
remain intact. This decision supersedes only D-0113's expectation that a
prepared reviewer must remain a transport-study fixture. The compatibility
schema recovery in D-0117 remains available for an otherwise evidence-complete
older writer; new role-first packets carry the SDK request schema directly as
an immutable input.

Reviewer task-family and output names are landing-specific only for landing
compatibility. Other duties use their writer family plus `_review` and the
neutral `independent_actor_review` output rather than masquerading as landing.

## Rationale

Admission class should describe the evidence and responsibility chain that
actually exists. Calling a fully formed independent actor a fixture hides the
stronger owner relation and leaves the durable system dependent on a temporary
landing compiler. The dedicated branch preserves strict byte and identity
checks while allowing eval, stats, memo, landing, and later duties to share one
physical runtime without giving `abyss-stack` authority to choose their role,
model, procedure, or acceptance outcome.

Keeping the legacy exporter unchanged preserves historical evidence and
regression coverage. Requiring transitive writer evidence and exact SDK schema
material prevents an independently launched reviewer from laundering an
unrelated result into A2A return.

## Consequences

- Positive: a role-first independently owned reviewer can now complete the
  same external CLI and A2A responsibility loop as its writer.
- Positive: the runtime surface remains model-neutral and task-family-neutral;
  Luna and eval selection are proof instances, not public API names.
- Positive: older writer evidence can be reviewed without rewriting history,
  while new packets use the preferred direct schema materialization.
- Tradeoff: role-first review packets are larger because their immutable
  evidence closure includes the exact writer task, result, report, outputs,
  and both SDK request contracts.
- Follow-up: install the validated content-addressed runtime, exercise distinct
  stats and memo obligations, and verify discovery from fresh Codex sessions
  before broad activation.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/prepare_landing_study.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

`aoa-agents` continues to own obligation, role, mandate, responsibility, and
return filtering; domain organs own their procedures and acceptance;
`aoa-models` owns fit observations; `aoa-sdk` owns incarnation and summon
meaning. `abyss-stack` owns only the exact external process, evidence-preserving
lifecycle, and reviewed transport return.
