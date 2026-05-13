# Runtime Lifecycle Landing Log

## 2026-05-07 - First-wave package landing

Created the runtime lifecycle package as a route home for deployment, layout,
up/down, smoke, logs, and systemd lifecycle surfaces.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-12 - Runtime status readout landing

Moved gateway cache status and usage snapshot schemas, examples, and validation
tests into the runtime-lifecycle package. Root policy and runbook docs stayed
root-facing because they remain operator orientation surfaces.

Validation route: package-local pytest, `python scripts/validate_stack.py`, and
`python scripts/validate_nested_agents.py`.

## 2026-05-13 - Part-local docs topology

Moved cache, usage, and internal-probe docs into the status-readouts and
wait-smoke parts. Root runbook and deployment docs remain repo-wide operator
entrypoints.

Validation route: `python scripts/validate_stack.py`.
