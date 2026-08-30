# Runtime Lifecycle Direction

This package keeps stack lifecycle explicit, operator-driven, and recoverable.

Current posture:

- keep install, layout, first-run, start/stop, warmup, wait/smoke, logs/status,
  status readouts, and user-unit routes separated by part
- keep stable root commands as wrappers
- keep service activation and unit enablement as explicit operator actions
- keep source checkout, deployed runtime root, and live runtime state distinct

Near direction:

- keep lifecycle docs aligned with source-only GitHub bootstrap
- keep layout checks aware of compatibility bridges without naming old routes
  as active topology
- add focused tests when status readouts or lifecycle wrappers gain new logic
- route host-fit questions to machine-fit and config material to
  config-projection
- keep the source-local LIVE code-intelligence observer provider-neutral,
  candidate/current/last-good, and explicit about machine admission and
  observation-meaning ownership
