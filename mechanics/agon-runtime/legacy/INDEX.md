# Agon Runtime Legacy Index

## Raw Docs

Old root docs now live in `legacy/raw/`:

- `docs/AGON_DUEL_EVENT_LOG_MODEL.md`
- `docs/AGON_DUEL_RUNTIME_KERNEL.md`
- `docs/AGON_DUEL_RUNTIME_STOP_LINES.md`
- `docs/AGON_MECHANICAL_TRIAL_EVENT_LOGS.md`
- `docs/AGON_MECHANICAL_TRIAL_RUNTIME.md`
- `docs/AGON_WAVE12_RUNTIME_LANDING.md`
- `docs/AGON_WAVE13_RUNTIME_LANDING.md`
- `docs/AGON_WAVE13_RUNTIME_STOP_LINES.md`

Old root quest stubs now live in `legacy/raw/quests/`:

- `quests/ABS-Q-AGON-0001-duel-runtime-kernel.md`
- `quests/ABS-Q-AGON-0002-event-log-hash-chain.md`
- `quests/ABS-Q-AGON-0003-mechanical-trial-runs.md`

## Artifacts

Old root artifacts were distilled into active `parts/runtime-kernels/` paths:

- `config/agon_*.seed.json` -> `parts/runtime-kernels/definitions/*.json`
- `generated/agon_*.min.json` -> `parts/runtime-kernels/generated/*.min.json`
- `examples/agon_*` -> `parts/runtime-kernels/examples/*.example.json`
- `schemas/agon-*.schema.json` -> `parts/runtime-kernels/schemas/*.schema.json`
- `scripts/*agon*` -> `parts/runtime-kernels/*.py`
- `tests/test_agon_*` -> `parts/runtime-kernels/tests/test_*.py`
- `manifests/recurrence/component.agon.*` -> `parts/runtime-kernels/recurrence/component.*.json`
- `manifests/recurrence/hooks/component.agon.*` -> `parts/runtime-kernels/recurrence/hooks/component.*.hooks.json`

`legacy/artifacts/README.md` remains only to explain where the old technical
artifact family went.

## Active Bridge

Start at `../README.md`. Use legacy files only when you need lineage. Use
`../parts/runtime-kernels/` for runnable dry-run proof.
Use `ARCHIVE_CLASSIFICATION.md` before promoting any raw document or old quest
stub into an active part.
