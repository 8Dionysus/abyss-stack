# Runtime Lifecycle Surfaces

This directory carries source-safe machine-readable contracts for lifecycle
status readouts.

## Status Readouts

- `schemas/runtime-gateway-cache-status.schema.json` defines the cache-lane
  status artifact described by `docs/GATEWAY_CACHE_POLICY.md`.
- `schemas/runtime-usage-snapshot.schema.json` defines the usage-pressure
  status artifact described by `docs/USAGE_BUDGET_POLICY.md`.
- `examples/` carries public-safe sample payloads used by
  `scripts/validate_stack.py` and package-local tests.

These contracts describe optional log artifacts. They do not prove live service
state, add endpoints, or create billing, routing, or quality authority.
