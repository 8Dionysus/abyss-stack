# Runtime Lifecycle Provenance

This package descends from deployment, first-run, runbook, lifecycle wrappers,
systemd unit, status, and layout helpers that define how the source checkout
becomes an operator-run runtime.

The refactor pattern is:

- keep public operator commands in `scripts/`
- keep implementation bodies under `mechanics/runtime-lifecycle/parts/`
- keep root docs as repo-wide operator routes when they are broader than one
  part
- keep live runtime state out of source history

## Owner Boundary

`abyss-stack` owns lifecycle wrappers, source/deployed path expectations,
rootless Podman posture, systemd user-unit skeletons, and public-safe runbook
docs. The host OS, Podman, systemd, `abyss-machine`, and the operator own live
activation, persistence, storage mutation, and service state.

## Current Bridges

- [PARTS.md](PARTS.md) maps lifecycle commands and root docs to package parts.
- [parts/layout-install/README.md](parts/layout-install/README.md) owns layout
  install and check routes.
- [parts/first-run-bootstrap/README.md](parts/first-run-bootstrap/README.md)
  owns first-run bootstrap routing.
- [parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md](parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md)
  and [parts/status-readouts/docs/USAGE_BUDGET_POLICY.md](parts/status-readouts/docs/USAGE_BUDGET_POLICY.md)
  own source-safe status readout contracts.
- [parts/live-code-intelligence/README.md](parts/live-code-intelligence/README.md)
  owns the source-local LIVE observation candidate, its state transitions, and
  its provider-neutral machine boundary.
- [../config-projection/README.md](../config-projection/README.md) owns
  config material and [../machine-fit/README.md](../machine-fit/README.md)
  owns host fit.
