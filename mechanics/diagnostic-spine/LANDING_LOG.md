# Diagnostic Spine Landing Log

## 2026-05-07 - Initial package landing

Created the diagnostic spine package as a route home for readiness checks,
truth-goal status, diagnostic artifacts, anchors, and repair handoff candidates.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Part-local docs topology

Moved diagnostic spine authority, doctor-readiness, local-ops split, and truth
surface docs into their owning parts. Rebuilt the diagnostic surface catalog so
its authority ref follows the active diagnostic spine doc.

Validation route: `python scripts/validate_stack.py`,
`python scripts/build_diagnostic_surface_catalog.py --check`, and
`python scripts/validate_diagnostic_surface_catalog.py`.
