# Package-Wide Mechanics Docs on Demand

- Decision ID: ABYSS-STACK-D-0143
- Status: accepted
- Date: 2026-09-05
- Owner surface: `mechanics/` package topology and validation

## Index Metadata

- Original date: 2026-09-05
- Surface classes: root/topology, validation guard, docs route
- Stack lanes: mechanics, decision lane
- Mechanic parents: all mechanics packages
- Guard families: mechanics topology, package route
- Posture: accepted topology rationale; no runtime or deployment change

## Context

The mechanics packages contain empty `docs/README.md` route indexes even when
their actual package-wide prose is absent and the active part routes already
identify the real contracts. Keeping those placeholders creates duplicate
routes and makes the package topology validator require a surface that carries
no package meaning.

## Options considered

- Keep the empty package indexes as permanent topology markers.
- Create an in-tree archive for the empty indexes.
- Route directly to current package and part owners, creating package-wide
  docs only when real package-wide prose is admitted.

## Decision

Package-wide `docs/` is optional. A package may create it when it has real
package-wide prose; an empty route index or future reservation is not required.
Package cards, `PARTS.md`, part indexes, actual part docs, and provenance remain
the active route and contract surfaces.

## Rationale

All removed placeholders are recoverable from the exact baseline commit and
original paths. Existing package and part routes already identify the narrower
owners, so direct routing removes competing maps without changing runtime
behavior, deployment, security, stronger-owner, or publication contracts.

This decision supersedes only the 2026-05-13 continuation of
`ABYSS-STACK-D-0002` that retained package docs route indexes; the meaningful
package-card spine in `ABYSS-STACK-D-0015` is unchanged. Recover the removed
paths from baseline `9af3697a6b3a98fa0404573f78466b795943683f` at:
`mechanics/{agon-runtime,config-projection,diagnostic-spine,experience-runtime,
federation-seams,governed-execution,inference-pilots,machine-fit,
runtime-lifecycle,runtime-repair}/docs/README.md`. No archive is added; current
package `PARTS.md` and part-local routes remain authoritative.

## Consequences

- Positive: package topology reflects content-bearing surfaces and avoids
  duplicate route indexes.
- Tradeoff: future package-wide prose must create `docs/` on demand.
- Follow-up: the topology validator requires package cards and active part
  contracts, while focused tests preserve the missing-part-doc failure guard.

## Source surfaces

- `mechanics/AGENTS.md`
- `mechanics/README.md`
- `mechanics/ARTIFACT_TOPOLOGY.md`
- `scripts/validators/mechanics_topology.py`
- `tests/test_mechanics_topology_validator_module.py`
- `mechanics/config-projection/PROVENANCE.md`

## Follow-up route

Use the owning package or part-local surface when package-wide prose becomes
real; regenerate decision indexes and affected KAG projections through their
canonical builders.
