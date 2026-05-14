# 2026-05-14 Entry Route Contract And Validation Placement

Status: accepted
Date: 2026-05-14

## Context

The root `README.md` had become a much cleaner source-checkout front door, but
its validation section still carried concrete command blocks, including
diagnostic-spine package commands. That repeated a pattern already solved in
`Agents-of-Abyss`: entry surfaces become noisy when they carry every local
validation lane directly.

`abyss-stack` needs the same principle adapted to runtime ownership. The stack
front door should name the broad validation route and point to the authority
surfaces that own exact commands. It should not become the command catalog for
diagnostic spine, mechanics packages, tests, or scripts.

## Options considered

1. Keep the command blocks in `README.md` because they are useful and short.
2. Delete the validation section entirely and rely on agents to find
   `AGENTS.md`.
3. Add a runtime-specific route contract, keep README as the entry surface, and
   move exact command authority to `AGENTS.md`, local cards, `scripts/README.md`,
   `tests/README.md`, and package-local mechanic surfaces.

## Decision

Use option 3.

Add `docs/START_HERE_ROUTE_CONTRACT.md` as the route-mode contract for
`abyss-stack` source checkout entry surfaces.

Root `README.md` now points to that route contract and names
`scripts/release_check.py` as the broad release-facing or repo-wide validation
gate. Exact command lanes stay in root `AGENTS.md`, nearest nested
`AGENTS.md`, `scripts/README.md`, `tests/README.md`, and package-local
mechanic cards.

Diagnostic catalog commands remain discoverable through diagnostic-spine and
scripts surfaces, but they no longer live in the root README front door.

## Rationale

This keeps the front door readable without weakening validation. The exact
commands remain closer to the surfaces that own them, where future changes are
less likely to create stale copies.

The route contract also gives root and docs entry surfaces a named place for
route-mode meaning, instead of relying on repeated tables in README and
AGENTS.md to stay aligned by memory.

## Consequences

- `README.md` stays route-focused and public-readable.
- Future route-mode changes must update the route contract, root entry
  surfaces, validators, tests, and changelog together.
- Package-specific validation commands should not be reintroduced into root
  README unless the route contract itself changes.
- Broad validation remains discoverable through `scripts/release_check.py`.

## Source surfaces

- `README.md`
- `AGENTS.md`
- `docs/START_HERE_ROUTE_CONTRACT.md`
- `docs/README.md`
- `docs/AGENTS.md`
- `scripts/validate_stack.py`
- `tests/test_current_direction_routes.py`

## Follow-up route

Revisit this decision only if the route contract becomes too thin to guide
entry surfaces or too broad and starts duplicating package-local cards.
