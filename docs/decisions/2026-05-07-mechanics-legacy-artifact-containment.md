# 2026-05-07 Mechanics Legacy Artifact Containment

## Status

Accepted.

## Context

The first mechanics refactor created convex package homes under `mechanics/`.
The repository still had old flat artifact families whose names carried wave,
seed, phase, and raw version scaffolding across `docs/`, `config/`,
`generated/`, `examples/`, `schemas/`, `scripts/`, `tests/`, and recurrence
manifests.

Two families were ready to move as bounded units:

- Agon dry-run runtime kernels and mechanical trial artifacts.
- Experience seed-derived runtime contracts, examples, and wave tests.

The sibling `Agents-of-Abyss` refactor showed the useful pattern: active
mechanic package route first, detailed old material under package-local
`legacy`, and explicit provenance bridges instead of keeping noisy flat names
as the current route.

## Options

1. Keep the flat files in root folders until every active name is redesigned.
2. Move old files directly into active package docs, schemas, scripts, and tests
   folders.
3. Move bounded old families into package-local `legacy` with provenance,
   indexes, distillation logs, and updated validators.

## Decision

Use option 3.

`abyss-stack` now contains `mechanics/agon-runtime` and
`mechanics/experience-runtime`. Old noisy file names are preserved under
package-local `legacy/raw` or `legacy/artifacts`, while active package cards,
`PROVENANCE.md`, `legacy/INDEX.md`, and `legacy/DISTILLATION_LOG.md` explain the
route.

## Rationale

This removes flat topology without pretending that old wave and seed names are
clean active contracts. It also keeps runnable artifacts testable: Agon builders
and validators moved with their config/generated/example/test surfaces, and
experience contract tests now read package-local schemas and examples.

The choice preserves stronger-owner boundaries. `Agents-of-Abyss` still owns
Agon and experience meaning; `Tree-of-Sophia` still owns authored meaning and
write stop-lines. `abyss-stack` owns only the runtime-side containment and
validation shape.

## Consequences

- Root `docs/`, `schemas/`, `examples`, `tests`, `scripts`, `generated`,
  `config`, and recurrence manifest surfaces are less flat for these families.
- Future edits must start from the package route, not the old root path.
- Legacy files remain reviewable but are not the first active source route.
- A later distillation pass can promote quiet active names out of `legacy` only
  when one runtime service, storage path, or validator clearly owns the surface.

