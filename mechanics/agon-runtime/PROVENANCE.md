# Agon Runtime Provenance

This package descends from the flat Agon runtime artifacts that previously
lived across root `docs/`, `config/`, `generated/`, `examples/`, `schemas/`,
`scripts/`, `tests/`, `quests/`, and `manifests/`.

The AOA pattern being mirrored is:

- active route first
- raw historical sources in the immutable Git snapshot below
- technical runnable artifacts distilled into active `parts/runtime-kernels/`
- an index that maps old names to their current package path
- no claim that archived raw files are current doctrine

## Owner Boundary

`Agents-of-Abyss` remains the stronger owner for Agon meaning. This package
only preserves the `abyss-stack` runtime-side dry-run substrate and validates
that it cannot mutate live authority.

## Active Contracts and Historical Recovery

- [parts/runtime-kernels/docs/RUNTIME_KERNELS.md](parts/runtime-kernels/docs/RUNTIME_KERNELS.md)
  describes the active dry-run substrate.
- [legacy/INDEX.md](https://github.com/8Dionysus/abyss-stack/blob/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/agon-runtime/legacy/INDEX.md) records the old flat-to-package mapping at that commit.
- [legacy/DISTILLATION_LOG.md](https://github.com/8Dionysus/abyss-stack/blob/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/agon-runtime/legacy/DISTILLATION_LOG.md) records what has and
  has not been distilled out of the archive.
- [legacy/ARCHIVE_CLASSIFICATION.md](https://github.com/8Dionysus/abyss-stack/blob/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/agon-runtime/legacy/ARCHIVE_CLASSIFICATION.md) records
  why raw wave-era docs and old `ABS-Q-AGON-*` quest stubs remain
  provenance-only unless a concrete runtime-kernel consumer is promoted.
- The historical artifact receipt records the old technical
  artifact family; active validation now runs from `parts/runtime-kernels/`.
