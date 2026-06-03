# Mechanics Package Card Completeness

- Decision ID: ABYSS-STACK-D-0015
- Status: accepted
- Date: 2026-05-13
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-13
- Surface classes: mechanic package, docs route
- Stack lanes: runtime mechanics
- Mechanic parents: cross-mechanic
- Guard families: docs route, validation lane
- Posture: accepted package-card rationale

## Context

After the mechanics topology refactor, several packages had strong `README.md`,
`AGENTS.md`, `PARTS.md`, `parts/README.md`, and `docs/README.md` surfaces, but
only the archive-heavy or later-distilled packages carried the full package-card
spine: `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and `LANDING_LOG.md`.

That left future passes with uneven handoff surfaces. The packages were already
convex enough to deserve the same route shape, but adding identical boilerplate
would have hidden the real owner differences.

## Options considered

1. Leave package-card completeness uneven.
2. Add identical boilerplate files to every package.
3. Add package-specific cards and make the shared package-card spine validator-backed.

## Decision

Every mechanics package must carry:

- `DIRECTION.md` for current contour
- `PROVENANCE.md` for lineage, owner-boundary bridges, and stop-lines
- `ROADMAP.md` for next movements and deferred moves
- `LANDING_LOG.md` for checked topology landings

The six previously incomplete packages now have package-specific cards:

- `config-projection`
- `diagnostic-spine`
- `federation-seams`
- `governed-execution`
- `machine-fit`
- `runtime-lifecycle`

`scripts/validate_stack.py` now requires `PROVENANCE.md` alongside the existing
package card files for every mechanics package.

## Rationale

Uneven package cards force future agents to rediscover where direction, provenance, landing history, and deferred work live. The shared spine makes route expectations predictable, while package-specific text prevents the cards from becoming copied ceremony.

## Consequences

- Future mechanics changes have a consistent route spine across all packages.
- Package cards can stay short because lineage and future movement have their
  own homes.
- The standard is validated rather than remembered from previous sessions.
- The cards must stay package-specific; copying boilerplate is a regression.

## Source surfaces

- `mechanics/<package>/DIRECTION.md`
- `mechanics/<package>/PROVENANCE.md`
- `mechanics/<package>/ROADMAP.md`
- `mechanics/<package>/LANDING_LOG.md`
- `scripts/validate_stack.py`

## Follow-up route

When adding or reshaping mechanics packages, update the full card spine and validator expectations in the same pass.
