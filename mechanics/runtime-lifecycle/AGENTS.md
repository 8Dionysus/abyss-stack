# AGENTS.md

Applies to `mechanics/runtime-lifecycle/`.

This package owns the route shape for install, layout, start, stop, wait,
smoke, logs, systemd user units, and operator runbook flow.
Current lifecycle docs include `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, and
`docs/RUNBOOK.md`.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not start services, enable units, widen host exposure, or mutate live state
from this package. Runtime activation remains an explicit operator action.

Validation:

```bash
python scripts/validate_stack.py
python -m pytest mechanics/runtime-lifecycle/parts/status-readouts/tests/test_runtime_hygiene.py -q
bash -n scripts/aoa-up scripts/aoa-down scripts/aoa-wait scripts/aoa-smoke scripts/aoa-logs
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
```
