# Experience Runtime Provenance

This package descends from flat runtime experience surfaces that carried old
wave, seed, and `_v1` naming.

The refactor mirrors the AOA archive pattern:

- keep active package route short
- archive old source names under `legacy/`
- keep an archive index and distillation log
- route stronger owner meaning away from `abyss-stack`

## Owner Boundary

`abyss-stack` owns runtime contract shape here. `Agents-of-Abyss` owns the
experience program and governance meaning. `Tree-of-Sophia` owns authored
meaning and write stop-lines.

## Current Bridges

- [parts/experience-records/docs/EXPERIENCE_RECORDS_DISTILLATION.md](parts/experience-records/docs/EXPERIENCE_RECORDS_DISTILLATION.md)
  records the active/archive classification.
- [legacy/INDEX.md](legacy/INDEX.md) maps old root families to current paths.
- [legacy/DISTILLATION_LOG.md](legacy/DISTILLATION_LOG.md) records what remains
  raw archive.
- [legacy/ARCHIVE_CLASSIFICATION.md](legacy/ARCHIVE_CLASSIFICATION.md) records
  why each preserved family remains archive-only until a concrete runtime
  consumer exists.
- `legacy/artifacts/tests/` proves the package-local schemas and examples.
