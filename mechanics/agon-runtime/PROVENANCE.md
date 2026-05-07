# Agon Runtime Provenance

This package descends from the flat Agon runtime artifacts that previously
lived across root `docs/`, `config/`, `generated/`, `examples/`, `schemas/`,
`scripts/`, `tests/`, and `manifests/`.

The AOA pattern being mirrored is:

- active route first
- raw historical sources in `legacy/raw`
- technical runnable artifacts in `legacy/artifacts`
- an index that maps old names to their current package path
- no claim that legacy raw files are current doctrine

## Owner Boundary

`Agents-of-Abyss` remains the stronger owner for Agon meaning. This package
only preserves the `abyss-stack` runtime-side dry-run substrate and validates
that it cannot mutate live authority.

## Current Bridges

- [legacy/INDEX.md](legacy/INDEX.md) maps old flat paths to package-local paths.
- [legacy/DISTILLATION_LOG.md](legacy/DISTILLATION_LOG.md) records what has and
  has not been distilled out of legacy.
- `legacy/artifacts/scripts/` remains runnable for narrow validation.

