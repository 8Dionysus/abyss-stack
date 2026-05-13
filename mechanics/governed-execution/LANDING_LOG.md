# Governed Execution Landing Log

## 2026-05-07 - Initial package landing

Created the governed execution package as a route home for autonomy gates,
governed local-worker runs, return policy, and candidate exports.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Part-local docs topology

Moved governed runner, recurrence/return-policy, and context-budget docs into
their owning parts while keeping runtime policy templates under
`config-templates/`.

Validation route: `python scripts/validate_stack.py`.
