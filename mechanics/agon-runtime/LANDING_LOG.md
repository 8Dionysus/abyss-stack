# Agon Runtime Landing Log

## 2026-05-07 - Archive topology landing

- Created the `agon-runtime` mechanics package.
- Moved old flat Agon runtime docs and artifacts into package-local `legacy`.
- Added provenance and archive index surfaces for follow-up validation.

Validation follows the package `AGENTS.md` route after path rewrites and test
execution.

## 2026-05-13 - Runtime kernels active distillation

- Promoted the runnable dry-run artifact family out of `legacy/artifacts/`.
- Renamed old `config`, seed, script, schema, example, generated, test, and
  recurrence paths into quiet `parts/runtime-kernels/` surfaces.
- Left raw `AGON_*` and landing notes in `legacy/raw/` as lineage only.
