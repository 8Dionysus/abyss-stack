# Runtime Lifecycle Landing Log

## 2026-05-07 - Initial package landing

Created the runtime-lifecycle package as the route home for install, layout,
start, stop, wait, smoke, logs, status, warmup, systemd user units, and
operator runbook flow.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Wrapper/backend topology

Kept stable root command wrappers while moving lifecycle implementation bodies
into package parts for layout, first-run, start/stop, wait/smoke, logs/status,
and user-unit helpers.

Validation route: shell syntax checks, status-readout tests, systemd user-unit
verification where available, and `python scripts/validate_stack.py`.

## 2026-05-13 - Package card completion

Added package-local `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and this
landing log so lifecycle changes keep source/runtime and operator-action
boundaries explicit.

## 2026-05-13 - Residual frontier alignment

Kept remaining live-runtime work as explicit packets rather than source claims.
Runtime lifecycle should apply those packet patterns only through explicit
operator actions after source validation and parity checks are green.

## 2026-05-13 - live runtime cutover and source runtime parity packets

Added package-local packet routes for source/runtime parity and live runtime cutover
cutover inspection. The parity packet may update the deployed `Configs` mirror;
the cutover packet remains read-only until an operator explicitly chooses a
start, stop, restart, systemd, profile, or exposure-changing action.

## 2026-07-13 - Loopback MCP owner lifecycle

Added a source-owned user-unit template and bundle for one shared process per
local MCP owner while retaining package-level stdio defaults. The lifecycle is
loopback-only, launches deployed Configs wrappers, preserves existing unit
masks, and requires bounded source/deployed preview, parity, and per-owner
canaries before restart. See `ABYSS-STACK-D-0077`.
