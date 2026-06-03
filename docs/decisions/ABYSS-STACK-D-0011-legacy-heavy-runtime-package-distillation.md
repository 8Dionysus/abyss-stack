# Legacy-Heavy Runtime Package Distillation

- Decision ID: ABYSS-STACK-D-0011
- Status: accepted
- Date: 2026-05-13
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-13
- Surface classes: mechanic package, legacy/provenance
- Stack lanes: runtime mechanics
- Mechanic parents: agon-runtime, experience-runtime
- Guard families: legacy containment, docs route
- Posture: accepted distillation rationale

## Context

`mechanics/agon-runtime` and `mechanics/experience-runtime` both looked
legacy-heavy after the mechanics topology refactor. The important question was
not file count, but whether the preserved payload was archive-only or already
had a clear runtime owner.

The existing containment rule allows promotion out of `legacy/` only when one
runtime service, storage path, validator, or operator route clearly owns the
surface.

## Options considered

1. Keep both Agon and Experience runtime families in `legacy/`.
2. Promote both families into active parts immediately.
3. Promote only the Agon runnable runtime substrate and leave Experience archive-bound.

## Decision

Promote the Agon dry-run runtime artifact family into
`mechanics/agon-runtime/parts/runtime-kernels/`.

Keep the Experience runtime contract family in
`mechanics/experience-runtime/legacy/` and add an active distillation stop-line
under `parts/experience-records/docs/`.

## Rationale

Agon had active validators, builders, simulations, generated registries,
examples, schemas, tests, and recurrence observations that already formed one
bounded runtime substrate. Keeping that runnable substrate under
`legacy/artifacts/` made legacy look active and kept old flat names alive.

Experience had valuable schemas, examples, and tests, but no current
`abyss-stack` service, storage path, operator command, or runtime validator that
consumes the family as an active contract. Several surfaces also route meaning
or authority to `Agents-of-Abyss` and `Tree-of-Sophia`.

## Consequences

- Agon active files use quiet package-local names under `parts/runtime-kernels/`.
- Agon raw `AGON_*` docs and old quest stubs remain lineage under `legacy/raw/`.
- `legacy/artifacts/` in Agon is now a marker, not a runnable home.
- Experience `_v1`, wave, and old contract-family names remain contained under
  `legacy/`.
- Future Experience promotion must start from one concrete runtime consumer and
  move docs, schemas, examples, tests, validators, and lineage together.

## Source surfaces

- `mechanics/agon-runtime/parts/runtime-kernels/`
- `mechanics/agon-runtime/legacy/`
- `mechanics/experience-runtime/legacy/`
- `mechanics/experience-runtime/parts/experience-records/docs/EXPERIENCE_RECORDS_DISTILLATION.md`

## Follow-up route

Revisit Experience promotion only when a concrete `abyss-stack` runtime consumer appears and can own docs, schemas, examples, tests, and validation together.
