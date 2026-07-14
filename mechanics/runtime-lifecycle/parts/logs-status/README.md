# Logs And Status

Routes `scripts/aoa-logs`, `scripts/aoa-status`,
`mechanics/runtime-lifecycle/parts/logs-status/aoa_logs.sh`,
`mechanics/runtime-lifecycle/parts/logs-status/aoa_status.sh`,
`mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`,
`mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md`, and `mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md`.

This part owns runtime readout posture; machine-readable contracts live in
`parts/status-readouts/`.

Use `scripts/aoa-status --resource-guards` when the operator needs to compare
the staged systemd compose selection with the cgroup limits on already-running
containers. This readout does not restart services; it names which resource
guards are applied and which are staged until the next controlled runtime
restart or reload. Its JSON summary exposes both `counts` and flat
`applied`/`staged_not_applied`/`missing_live_container` counters so apply gates
can make simple readiness decisions without parsing the service list.

Use `scripts/aoa-status --service-selection` to compare running Compose
containers with `docs/runtime/service-selection-policy.v1.json`. This catches
selected services that are missing and opt-in, fallback, lab, or unknown services
that are unexpectedly running. Its JSON summary mirrors the resource-guard
readout pattern with flat counters such as `running_selected`,
`missing_selected`, `unexpected_running`, and `unknown_running`, while retaining
the nested `counts` map. It also exposes
`abyss-stack/selected-service-running-coverage-ratio` over every
`selected_now` policy entry. A successful observation with no running selected
services is zero; an unavailable container observation or an empty selected
population is unknown.

Use `scripts/aoa-status --optimization` for the operator-facing summary that
combines service selection, resource-guard application state, and
`abyss-machine` game-guard plus resource-plan readiness into one apply/no-apply
verdict. It is conservative: a blocked resource plan prevents `ready_to_apply`
even when the game guard is clear.

Use `scripts/aoa-status --optimization-audit` before claiming the service
optimization objective complete. It maps the prompt-level requirements to live
and source evidence: screenshot baseline, service policy, research packet,
resource overlays, user-unit selection, service-selection readout,
resource-guard readout, game guard, protected host units, and post-apply
evidence. Add `--require-complete` when a caller needs a hard completion gate;
it exits non-zero until every required audit check is `done`.
