# Runtime Repair Provenance

This package preserves the runtime repair artifact family that used to be split
across root `docs/`, `schemas/`, `examples/`, and `tests`.

The active repair route stays in this package and the standing docs:

- `README.md`
- `DIRECTION.md`
- `PARTS.md`
- `docs/ANTIFRAGILITY_RUNTIME.md`
- `docs/REPAIR_SAFE_CLOSEOUT.md`

Old wave and `_v1` artifacts now live in package-local `legacy`.

## Owner Boundary

`abyss-stack` owns runtime-side degradation evidence, closeout receipt contract
shape, and public-safe examples. Actual repair, remediation, memory truth, and
owner-repo proof stay with operator action, `aoa-skills`, `aoa-sdk`, and the
affected owner repositories.

## Current Bridges

- [legacy/INDEX.md](legacy/INDEX.md) maps old root paths to current legacy paths.
- [legacy/DISTILLATION_LOG.md](legacy/DISTILLATION_LOG.md) records what remains
  legacy.
- `legacy/artifacts/tests/` keeps the receipt schema/example contract runnable.
