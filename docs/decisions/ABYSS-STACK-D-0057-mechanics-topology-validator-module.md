# Mechanics Topology Validator Module

- Decision ID: ABYSS-STACK-D-0057
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/mechanics_topology.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, mechanic topology, docs route
- Stack lanes: source checkout, runtime mechanics, docs and routes
- Mechanic parents: cross-mechanic
- Guard families: validation lane, mechanics topology, archive posture, route card
- Posture: accepted sixteenth validator-module split

## Context

After the decision-surface split, `scripts/validate_stack.py` still held
mechanics topology contracts and the large constant set that defines mechanics
packages, parts, package card headings, required files, archive required
surfaces, and marker-only archive artifact posture.

This surface protects the mechanics atlas and package-card spine. It is not a
runtime health check and it does not own mechanic-local behavior; it ensures
the source tree keeps coherent mechanics routes and does not reintroduce noisy
legacy material into active part routes.

## Options considered

- Keep mechanics topology checks and constants inside `scripts/validate_stack.py`.
- Split only the package list while leaving archive and part requirements in
  the root validator.
- Create a focused `scripts/validators/mechanics_topology.py` module.

## Decision

Create `scripts/validators/mechanics_topology.py` and move the implementation
of `validate_mechanics_topology` plus its mechanics package, part, archive,
heading, and active-part naming constants into it.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Mechanics topology is a cross-mechanic owner surface. Keeping the package list,
part map, archive posture, and package-card route law together makes it clear
that mechanics structure is validated as an atlas, not as scattered root-file
presence.

The root validator should orchestrate this check, not carry the mechanics
spine as internal mutable state.

## Consequences

- Positive: mechanics topology now has a focused owner module.
- Positive: direct module tests cover current repo validity, a synthetic
  minimal valid mechanics surface, atlas route drift, package-card heading
  drift, active legacy-like part names, and marker-only archive artifacts.
- Positive: root validator API compatibility remains intact.
- Tradeoff: the module carries a substantial constants surface because those
  constants are the mechanics topology contract.

## Source surfaces

- `scripts/validators/mechanics_topology.py`
- `scripts/validate_stack.py`
- `mechanics/README.md`
- `mechanics/*/README.md`
- `mechanics/*/PARTS.md`
- `mechanics/*/parts/README.md`
- `docs/runtime/MECHANICS.md`
- `tests/test_mechanics_topology_validator_module.py`

## Follow-up route

Candidate next splits are compose profile/preset topology or root
README/runtime path guards.
