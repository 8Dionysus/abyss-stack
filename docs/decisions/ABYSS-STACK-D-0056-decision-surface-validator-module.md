# Decision Surface Validator Module

- Decision ID: ABYSS-STACK-D-0056
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/decision_surface.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, decision route, docs route
- Stack lanes: source checkout, docs and routes, decision lane
- Mechanic parents: cross-mechanic
- Guard families: validation lane, decision surface, generated index handoff
- Posture: accepted fifteenth validator-module split

## Context

After the root-routes split, `scripts/validate_stack.py` still held decision
surface route checks. These checks protect `docs/decisions/README.md`,
`docs/decisions/AGENTS.md`, `docs/decisions/TEMPLATE.md`, and the surrounding
docs/scripts/tests handoff to decision validation commands.

The decision surface has two neighboring authorities:

- `scripts/validate_decision_records.py` validates record shape.
- `scripts/generate_decision_indexes.py` builds and checks generated indexes.

The remaining root validator logic was not those authorities; it was the route
law that keeps readers pointed at them.

## Options considered

- Keep decision route checks inside `scripts/validate_stack.py`.
- Merge them into `scripts/validate_decision_records.py`.
- Create a focused `scripts/validators/decision_surface.py` module.

## Decision

Create `scripts/validators/decision_surface.py` and move the implementation of
`validate_decision_record_surface` into it.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Decision records are rationale, not current runtime law. The route surface
around them must stay explicit so generated indexes remain read models, the
template keeps the canonical shape, and validation commands stay discoverable
from docs, scripts, and tests.

Keeping this as a focused validator module avoids making
`validate_decision_records.py` responsible for route-card documentation while
still preserving the handoff to the true decision-record validators.

## Consequences

- Positive: decision route-card drift now has a focused owner module.
- Positive: direct module tests cover generated-index route drift,
  generator-check route drift, and missing decision test routing.
- Positive: root validator API compatibility remains intact.
- Tradeoff: the module sits beside, not inside, the generated-index and record
  shape validators.

## Source surfaces

- `scripts/validators/decision_surface.py`
- `scripts/validate_stack.py`
- `docs/decisions/README.md`
- `docs/decisions/AGENTS.md`
- `docs/decisions/TEMPLATE.md`
- `docs/AGENTS.md`
- `scripts/README.md`
- `tests/README.md`
- `tests/test_decision_surface_validator_module.py`

## Follow-up route

Candidate next splits are mechanics topology contracts or root README
route-focus/runtime path guards.
