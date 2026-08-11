# Carry Owner-Contour Writers Through Independent A2A Review

- Decision ID: ABYSS-STACK-D-0113
- Status: accepted
- Date: 2026-08-11
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-11
- Surface classes: runtime boundary, actor admission, independent review, A2A return
- Stack lanes: source, runtime, review
- Mechanic parents: governed-execution
- Guard families: owner provenance, exact binding, effect ceiling, independent review
- Posture: accepted owner-contour review seam; live role proof remains required

## Context

D-0112 made new owner-contour writers evidence-complete through summon v4 and
SDK incarnation binding v2. The existing reviewer preparer and A2A exporter
still accepted only historical `transport_study_fixture` writers, so a real
owner-contour result could reach `review_required` but could not enter the
already implemented independent-review and responsibility-return path.

The reviewer compiler already verifies the writer's durable result, report,
actor final manifest and delta, forwards stable immutable-input identities, and
requires a plan-bound read-only reviewer role and same-model/same-effort
realization. Rebuilding a second owner request for that derived reviewer would
duplicate the writer's already admitted responsibility chain without adding a
new domain selection.

## Options considered

- Keep independent review limited to transport fixtures and treat real
  owner-contour writer results as manual-only evidence.
- Compile a second independent owner-contour responsibility transfer for every
  reviewer before any review can start.
- Admit an owner-contour writer into the existing prepared read-only reviewer
  path while preserving the writer's owner evidence and restricting export to
  one exact mixed admission pair.

## Decision

Canonical review preparation accepts terminal, failure-free writers from
either `transport_study_fixture` or `owner_contour`. An owner-contour writer
must retain its exact launch class across launch, durable state, and result, and
its binding v2 must validate against the writer plan before reviewer artifacts
are compiled.

The prepared reviewer remains a separately addressed
`transport_study_fixture` with `independent_review` posture, read-only tools,
no external effects, and an explicit role and realization that match the
reviewer ref already present in the writer plan. This class denotes the derived
review execution contour; it does not replace or downgrade the writer's owner
admission.

A2A export admits only two admission pairs:

- historical transport-study writer and transport-study reviewer;
- owner-contour writer and its prepared transport-study reviewer.

The exporter continues to require different sessions, incarnations, and Codex
threads; exact review-seed, result, report, event, actor-manifest, actor-delta,
summon-request, schema, task, owner, and parent bindings; zero reviewer delta;
and a terminal proceed or return-for-repair decision. SDK `a2a_remote` or
`either` remains valid for the owner writer, while the prepared reviewer keeps
its local derived-review transport.

Task `expected_artifacts` are the symbolic named outputs already admitted by
the owner request. Model report `artifact_paths` are concrete workspace files.
The A2A child result returns both classes and requires both summon requests to
be satisfied rather than pretending that a symbolic output name must equal a
workspace path.

## Rationale

The writer's responsibility chain is already owner-complete before launch.
Independent review is a derived verification obligation named in that plan,
not a new domain-owner selection. Reusing the strict review compiler preserves
the writer's evidence and gives the reviewer a separate physical body without
granting it coder authority or asking `abyss-stack` to choose a role or model.

Restricting the mixed pair explicitly prevents an arbitrary fixture from
laundering an owner result. Keeping symbolic outputs distinct from artifact
paths preserves both the mandate's domain vocabulary and the runtime's exact
filesystem evidence.

## Consequences

- Positive: a real owner-contour writer can now complete the intended
  writer-to-reviewer-to-A2A responsibility return.
- Positive: reviewer permissions remain read-only and independently bound.
- Positive: transport fixtures remain valid historical and regression
  evidence without becoming owner proof.
- Tradeoff: the prepared reviewer still uses a compatibility admission class;
  a future general obligation compiler may replace that class when reviewers
  acquire independently durable duties beyond one derived review.
- Follow-up: prove the mixed pair with the first Luna landing pilot, preserve
  failed and return-for-repair outcomes, and route observations to model fit,
  eval, stats, and memo owners without inferring acceptance.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`
- `mechanics/governed-execution/parts/external-codex-agent/prepare_landing_study.py`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`

## Follow-up route

`aoa-agents` remains the owner of the writer obligation, mandate, reviewer role,
and responsibility return; `aoa-models` remains the owner of current
realizations; `aoa-sdk` remains the owner of plan and binding meaning; and
`abyss-stack` owns only physical review preparation, lifecycle, evidence, and
A2A export. Revisit this decision when reviewer work becomes an independently
selected domain duty rather than a plan-derived verification branch.
