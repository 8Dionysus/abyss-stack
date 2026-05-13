# Runtime Repair Provenance

This package preserves the runtime repair artifact family that used to be split
across root `docs/`, `schemas/`, `examples/`, and `tests`.

The active repair route stays in this package and the standing docs:

- `README.md`
- `DIRECTION.md`
- `PARTS.md`
- `mechanics/runtime-repair/parts/antifragility-posture/docs/ANTIFRAGILITY_RUNTIME.md`
- `mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md`

Old wave docs live in package-local `legacy`. Active receipt artifacts live
under their owning parts.

## Owner Boundary

`abyss-stack` owns runtime-side degradation evidence, closeout receipt contract
shape, and public-safe examples. Actual repair, remediation, memory truth, and
owner-repo proof stay with operator action, `aoa-skills`, `aoa-sdk`, and the
affected owner repositories.

## Current Bridges

- [legacy/INDEX.md](legacy/INDEX.md) maps old root paths to current legacy paths.
- [legacy/DISTILLATION_LOG.md](legacy/DISTILLATION_LOG.md) records what remains
  legacy.
- `parts/degradation-receipts/tests/` and `parts/repair-safe-closeout/tests/`
  keep the receipt schema/example contracts runnable.
