# AGENTS.md

Applies to `mechanics/runtime-lifecycle/`.

This package owns the route shape for install, layout, start, stop, wait,
smoke, logs, systemd user units, and operator runbook flow.
Current lifecycle docs include `docs/install/DEPLOYMENT.md`, `docs/install/FIRST_RUN.md`, and
`docs/operations/RUNBOOK.md`.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not start services, enable units, widen host exposure, or mutate live state
from this package. Runtime activation remains an explicit operator action.

Validation:

```bash
python scripts/validate_stack.py
python -m pytest mechanics/runtime-lifecycle/parts/start-stop/tests/test_aoa_warmup.py -q
python -m pytest mechanics/runtime-lifecycle/parts/status-readouts/tests/test_runtime_hygiene.py -q
bash -n scripts/aoa-install-layout scripts/aoa-check-layout scripts/aoa-first-run scripts/aoa-up scripts/aoa-down scripts/aoa-warmup scripts/aoa-wait scripts/aoa-smoke scripts/aoa-logs scripts/aoa-status scripts/aoa-install-systemd
bash -n mechanics/runtime-lifecycle/parts/first-run-bootstrap/aoa_*.sh mechanics/runtime-lifecycle/parts/start-stop/aoa_*.sh mechanics/runtime-lifecycle/parts/wait-smoke/aoa_*.sh mechanics/runtime-lifecycle/parts/logs-status/aoa_*.sh mechanics/runtime-lifecycle/parts/layout-install/aoa_*.sh mechanics/runtime-lifecycle/parts/user-unit/aoa_*.sh
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
```
