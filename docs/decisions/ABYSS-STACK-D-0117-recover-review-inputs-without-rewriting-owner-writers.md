# Recover Review Inputs Without Rewriting Owner Writers

- Decision ID: ABYSS-STACK-D-0117
- Status: accepted
- Date: 2026-08-11
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-11
- Surface classes: runtime boundary, independent review, evidence compatibility
- Stack lanes: runtime, evidence, review
- Mechanic parents: governed-execution
- Guard families: immutable inputs, owner provenance, exact binding, fail closed
- Posture: accepted controller-derived review compatibility; no historical rewrite

## Context

The first accepted owner-contour Luna landing writer retained an exact SDK v4
summon request, durable source baseline, terminal result, report, actor final
manifest, delta, and thread. Its task was compiled before canonical reviewer
preparation required the selected workspace manifest and summon-request schema
to appear as explicit writer immutable inputs. The evidence existed, but not
under the later task-input ABI, so the writer could not enter the independent
review branch promised by D-0113.

Repeating the writer would spend model work and replace an already valid role
continuum. Editing its task, launch, or state would instead rewrite historical
evidence and invalidate the accepted result.

## Options considered

- Start a new writer under the newer task-input ABI and repeat the obligation.
- Add the missing IDs retroactively to the old task, launch, and durable state.
- Preserve the writer exactly and derive narrowly named reviewer inputs from
  evidence already bound by its terminal state and selected SDK source.

## Decision

Canonical reviewer preparation may recover the two missing inputs only for an
otherwise admitted `owner_contour` writer:

- `writer-source-baseline-manifest` is copied byte-for-byte from the canonical
  runtime-owned `source-manifest-before.json` only when its path and digest
  match both result and durable state, its JSON equals
  `workspace_manifest_baseline`, and its workspace path and Git HEAD match the
  writer launch;
- `writer-summon-request-schema` records a controller-derived exact-byte copy
  of the selected SDK v4 request schema only when the writer request already
  names that schema identity and version;
- the reviewer receives a separate active `summon-request-schema` input for
  its own SDK v4 request.

These are new review inputs, not backfilled claims about the writer task. Their
reserved IDs cannot collide with writer-owned inputs. The derived provenance
is added to the reviewer plan and continuation, while every original writer
artifact remains unchanged.

A2A export may use the reviewer's active exact SDK schema to validate a writer
whose task lacked the schema input only when the separately materialized
`writer-summon-request-schema` bytes are identical and its provenance names
that active schema. Both are revalidated under the reviewer lock immediately
before publication. Transport-study writers and owner writers that already
contain the canonical inputs keep the ordinary path unchanged.

## Rationale

The compatibility seam preserves responsibility continuity without pretending
that later controller requirements existed in the earlier task. The runtime
derives only facts it already owns or whose exact SDK bytes the caller selected;
it does not infer role, model, task, authority, effect, or acceptance. Distinct
input identities keep the evidence legible to future reviewers and make every
mismatch fail closed.

## Consequences

- Positive: an evidence-complete historical owner writer can reach its already
  planned reviewer and A2A return without another model run.
- Positive: original task, launch, result, state, report, thread, and actor
  artifacts remain immutable counterevidence.
- Positive: the compatibility path is model-neutral and does not widen reviewer
  permissions or domain scope.
- Tradeoff: reviewer tasks carry an explicit controller-derived compatibility
  pair in addition to their active SDK schema.
- Negative: an incomplete, changed, foreign, or non-owner writer still cannot
  use this route and must be repaired or rerun under its owning contour.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/prepare_landing_study.py`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

Carry the preserved Luna landing writer through the independently bound
read-only reviewer and A2A return. New writer compilers should continue to
include the canonical baseline and SDK schema directly; this compatibility
route remains for already admitted evidence, not as the preferred authoring
shape.
