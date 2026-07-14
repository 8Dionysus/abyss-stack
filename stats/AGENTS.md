# AGENTS.md

Local route card for `stats/` in `abyss-stack`.

## Applies to

Everything under `stats/` in `abyss-stack`.

## Role

This directory owns stack-local statistical questions and their measurement
contracts. Shared statistical grammar and cross-owner composition remain owned
by `aoa-stats`.

## Read before editing

1. Root `AGENTS.md`, `DESIGN.md`, and `BOUNDARIES.md`.
2. `stats/README.md` and `stats/port.manifest.json`.
3. `docs/runtime/service-selection-policy.v1.json` and the service-selection
   readout under `mechanics/runtime-lifecycle/parts/logs-status/`.
4. The central measurement and local-port contracts under `aoa-stats/stats/`.

## Boundaries

- `port.manifest.json` owns the stack-local question and measurement meaning.
- Live values remain in runtime readouts; do not commit a live packet or copy
  container state into this directory.
- Every `selected_now` policy entry stays in the denominator, including a
  missing selected service.
- A failed observation and an empty selected population are unknown, not zero.
- The ratio does not establish service health, quality, readiness over time, or
  authority to mutate the runtime.

## Validation

Manually exercise complete, partial, zero, empty-population, and unavailable-
observation cases against the service-selection read model before changing its
invariants. Then run:

```bash
python scripts/validate_local_stats_port.py
```

Use the root validation route for the implementation and source checkout.

## Closeout

Report the local question changed, manual cases inspected, runtime read model
affected, central protocol validation, and source validation.
