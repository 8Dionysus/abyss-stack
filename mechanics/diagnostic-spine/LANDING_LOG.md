# Diagnostic Spine Landing Log

## 2026-05-07 - Initial package landing

Created the diagnostic-spine package as the route home for doctor readiness,
diagnostic read models, truth-goal status, generated diagnostic catalogs, and
repair handoff candidates.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Part-local diagnostic surfaces

Moved active diagnostic docs, schemas, examples, generated catalog, and focused
tests under owning parts while keeping root wrappers stable.

Validation route: diagnostic catalog check/validate, focused pytest, and
`python scripts/validate_stack.py`.

## 2026-05-13 - Package card completion

Added package-local `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and this
landing log to make diagnostic ownership and repair stop-lines explicit.
