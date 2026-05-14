# 2026-05-14 Direction, History, And Decision Surface Roles

Status: accepted
Date: 2026-05-14

## Context

`abyss-stack` had already gained root `DESIGN.md`, `DESIGN.AGENTS.md`, mechanics
package cards, package-local roadmaps, landing logs, and decision records. The
next weak point was the source-of-truth split between root `README.md`,
`ROADMAP.md`, `CHANGELOG.md`, and `docs/decisions/`.

`Agents-of-Abyss` now uses a cleaner pattern:

- root roadmap owns current direction, horizons, and future triggers
- README stays the public front door and route surface
- changelog owns release-visible history
- decisions explain why a durable route or placement was chosen
- mechanic roadmaps, landing logs, provenance, and legacy surfaces keep local
  detail out of root

The same principle fits `abyss-stack`, but the content must stay runtime
specific. This repository owns runtime substrate direction, deployment posture,
source/runtime parity, machine fit, diagnostics, repair, and federation
consumption boundaries. It does not own AoA constitutional direction or ToS
authored meaning.

## Options considered

1. Keep root `README.md`, `ROADMAP.md`, `CHANGELOG.md`, and `docs/decisions/`
   as loosely related docs and rely on future agents to remember the
   distinction.
2. Copy the `Agents-of-Abyss` wording directly.
3. Adopt the same role split with `abyss-stack` runtime-specific authority,
   a decision-record validator, and local route cards.

## Decision

Use option 3.

Root `README.md` is the source checkout front door. It owns short entry
routing, route modes, claim checks, source/runtime boundary reminders, and a
compact current contour. It does not own package-local inventories, release
history, roadmap law, decision rationale, or live runtime receipts.

Root `ROADMAP.md` is the runtime-wide direction surface. It owns current
runtime direction, runtime horizons, source/runtime parity pressure, live
cutover pressure, machine-fit pressure, federation-consumption pressure,
diagnostic and repair posture, and concrete future triggers.

`CHANGELOG.md` is the release-visible history surface. It records public-safe
release and unreleased changes without becoming a roadmap, landing log, runtime
receipt, or decision record.

`docs/decisions/` is the durable rationale district. It now has a local
`AGENTS.md`, `TEMPLATE.md`, shape validator, tests, and release-check coverage.
All existing decision records use the standard `Status`, `Date`, `Options
considered`, `Rationale`, `Source surfaces`, and `Follow-up route` shape.

## Rationale

The previous split was readable only if the agent already knew the working
habit from recent sessions. That is too fragile for a repository that is being
cleaned for long-horizon source/install use.

Root README detail should not become a hidden current-state ledger. Root
roadmap history should not become a hidden changelog. Changelog entries should
not carry direction or rationale that belongs in root roadmap or decisions.
Decision records should not become current law just because they explain why
current law moved.

Validator-backed decision records make the rule durable without making the root
docs heavy. The root roadmap can now stay horizon-shaped, while local mechanics
continue to own their own roadmaps, landing logs, provenance bridges, and
legacy details.

## Consequences

- Future direction changes must decide whether they move runtime-wide direction
  or only mechanic-local direction.
- README stays route-focused and should not list every checked schema, example,
  test, generated file, receipt, or live command for a package-local surface.
- Release history belongs in `CHANGELOG.md`, not in root roadmap prose.
- Durable rationale belongs in `docs/decisions/` and must pass the decision
  record validator.
- Existing decision records are normalized rather than left as pre-contract
  drift.
- `scripts/release_check.py` now checks decision-record shape before the wider
  source release audit.

## Source surfaces

- `README.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/decisions/AGENTS.md`
- `docs/decisions/README.md`
- `docs/decisions/TEMPLATE.md`
- `scripts/validate_decision_records.py`
- `scripts/validate_stack.py`
- `scripts/release_check.py`
- `tests/test_decision_records.py`
- `tests/test_roadmap_parity.py`

## Follow-up route

Revisit this decision only if the root README again becomes an inventory
ledger, if the root roadmap again starts carrying release history, if
`CHANGELOG.md` starts carrying future direction or rationale, or if decision
records start replacing active source surfaces instead of explaining why they
changed.
