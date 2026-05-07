# AGENTS.md

Applies to `mechanics/agon-runtime/legacy/`.

This directory preserves old flat Agon runtime surfaces after the mechanics
topology refactor.

Use `../README.md` and `../PROVENANCE.md` before treating any legacy file as
evidence. Raw legacy docs in `legacy/raw/` are historical source material;
technical artifacts under `artifacts/` remain runnable only because validators
still prove them.

Do not:

- rename raw files casually
- move legacy files back to root folders
- treat a wave landing note as active runtime law
- hand-edit generated registries without running the builders

Validation:

```bash
python mechanics/agon-runtime/legacy/artifacts/scripts/build_agon_duel_runtime_kernel_registry.py --check
python mechanics/agon-runtime/legacy/artifacts/scripts/build_agon_mechanical_trial_run_registry.py --check
python -m pytest mechanics/agon-runtime/legacy/artifacts/tests
```
