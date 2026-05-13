# AGENTS.md

Applies to `mechanics/agon-runtime/legacy/`.

This directory preserves old flat Agon runtime surfaces after the mechanics
topology refactor.

Use `../README.md`, `../PROVENANCE.md`, `ARCHIVE_CLASSIFICATION.md`, and
`../parts/runtime-kernels/docs/RUNTIME_KERNELS.md` before treating any legacy
file as evidence. Raw legacy docs in `legacy/raw/` are historical source
material. The old technical artifact family has been distilled into
`../parts/runtime-kernels/`; `legacy/artifacts/` remains a marker only.

Do not:

- rename raw files casually
- move legacy files back to root folders
- treat a wave landing note as active runtime law
- treat old `ABS-Q-AGON-*` stubs as active root questbook records
- reintroduce runnable scripts, generated registries, schemas, examples, or
  tests under `legacy/artifacts/`

Validation:

```bash
python mechanics/agon-runtime/parts/runtime-kernels/build_duel_runtime_kernel_registry.py --check
python mechanics/agon-runtime/parts/runtime-kernels/build_mechanical_trial_run_registry.py --check
python -m pytest mechanics/agon-runtime/parts/runtime-kernels/tests
```
