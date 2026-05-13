# Mechanics Package Card Completeness

Date: 2026-05-13

## Status

Accepted.

## Context

After the mechanics topology refactor, several packages had strong `README.md`,
`AGENTS.md`, `PARTS.md`, `parts/README.md`, and `docs/README.md` surfaces, but
only the archive-heavy or later-distilled packages carried the full package-card
spine: `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and `LANDING_LOG.md`.

That left future passes with uneven handoff surfaces. The packages were already
convex enough to deserve the same route shape, but adding identical boilerplate
would have hidden the real owner differences.

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

## Consequences

- Future mechanics changes have a consistent route spine across all packages.
- Package cards can stay short because lineage and future movement have their
  own homes.
- The standard is validated rather than remembered from previous sessions.
- The cards must stay package-specific; copying boilerplate is a regression.
