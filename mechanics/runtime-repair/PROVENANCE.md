# Runtime Repair Provenance

This package preserves the runtime repair artifact family that used to be split
across root `docs/`, `schemas/`, `examples/`, and `tests`.

The active repair route stays in this package and the standing docs:

- `README.md`
- `DIRECTION.md`
- `PARTS.md`
- `mechanics/runtime-repair/parts/antifragility-posture/docs/ANTIFRAGILITY_RUNTIME.md`
- `mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md`

Old chaos-route docs remain in the immutable historical snapshot below. Active receipt artifacts live
under their owning parts.

## Owner Boundary

`abyss-stack` owns runtime-side degradation evidence, closeout receipt contract
shape, and public-safe examples. Actual repair, remediation, memory truth, and
owner-repo proof stay with operator action, `aoa-skills`, `aoa-sdk`, and the
affected owner repositories.

## Active Contracts and Historical Recovery

- [legacy/INDEX.md](https://github.com/8Dionysus/abyss-stack/blob/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/runtime-repair/legacy/INDEX.md) records the old root-to-archive mapping at that commit.
- [legacy/DISTILLATION_LOG.md](https://github.com/8Dionysus/abyss-stack/blob/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/runtime-repair/legacy/DISTILLATION_LOG.md) records what remains
  archived.
- `parts/degradation-receipts/tests/` and `parts/repair-safe-closeout/tests/`
  keep the receipt schema/example contracts runnable.
