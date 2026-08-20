# Runtime Lifecycle Landing Log

## 2026-05-07 - Initial package landing

Created the runtime-lifecycle package as the route home for install, layout,
start, stop, wait, smoke, logs, status, warmup, systemd user units, and
operator runbook flow.

Validation followed the package and root validation routes.

## 2026-05-13 - Wrapper/backend topology

Kept stable root command wrappers while moving lifecycle implementation bodies
into package parts for layout, first-run, start/stop, wait/smoke, logs/status,
and user-unit helpers.

Validation covered shell syntax, status-readout tests, systemd user-unit
verification where available, and the root source route.

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

## 2026-08-20 - Two-phase stack MCP runtime repair

Separated manual offline provisioning from guarded automatic repair. Automatic
repair now builds and validates a replacement while the production read plane
remains available, excludes non-read planes with an operation lock, and limits
quiescence to the final atomic swap. Dependency failure does not stop readers;
all direct shared-venv consumers are lock-aware, and the final swap enumerates
the active organ readers. Post-quiesce failure restores the prior runtime and
every previously active reader; the stack peer uses an exact, private, read-only
rollback grant.
