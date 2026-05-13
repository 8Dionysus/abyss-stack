# Federation Seams Landing Log

## 2026-05-07 - Initial package landing

Created the federation-seams package as the route home for runtime consumption
of sibling owner surfaces, advisory mirrors, route-api posture, and federation
sync checks.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - RPG and compatibility containment

Kept RPG runtime projection generated surfaces under their owning part and
moved upstream compatibility identifiers behind explicit compatibility bridges
and legacy inventory.

Validation route: RPG projection check, focused pytest, py_compile, and
`python scripts/validate_stack.py`.

## 2026-05-13 - Package card completion

Added package-local `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and this
landing log so federation seam changes have an explicit owner-boundary spine.
