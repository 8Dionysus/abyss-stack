# Runtime Lifecycle Surfaces

This directory carries source-safe machine-readable contracts for lifecycle
status readouts.

## Status Readouts

- `docs/GATEWAY_CACHE_POLICY.md` owns the gateway cache status posture.
- `docs/USAGE_BUDGET_POLICY.md` owns runtime usage and pressure posture.
- `schemas/runtime-gateway-cache-status.schema.json` defines the cache-lane
  status artifact described by `mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md`.
- `schemas/runtime-usage-snapshot.schema.json` defines the usage-pressure
  status artifact described by `mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md`.
- `examples/` carries public-safe sample payloads used by
  `scripts/validate_stack.py` and package-local tests.

These contracts describe optional log artifacts. They do not prove live service
state, add endpoints, or create billing, routing, or quality authority.
