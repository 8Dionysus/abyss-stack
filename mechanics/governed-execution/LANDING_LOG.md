# Governed Execution Landing Log

## 2026-05-07 - Initial package landing

Created the governed-execution package as the route home for governed local
worker execution, autonomy-gate reporting, return policy, candidate export, and
reviewable run records.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Part-local runner and candidate surfaces

Kept root wrappers stable while moving governed-runner, autonomy-status,
return-policy, local-worker-path, runtime-contract, and candidate-export
surfaces into package parts with focused tests and validators.

Validation route: focused governed-execution pytest, py_compile, and
`python scripts/validate_stack.py`.

## 2026-05-13 - Package card completion

Added package-local `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and this
landing log so governed execution changes have explicit review and owner
handoff boundaries.
