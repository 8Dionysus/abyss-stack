# AGENTS.md

Applies to `mechanics/runtime-repair/legacy/`.

This directory preserves old runtime repair wave and `_v1` receipt artifacts
after the mechanics topology refactor.

Use `../README.md` and `../PROVENANCE.md` before treating a legacy artifact as
current evidence. Raw docs in `legacy/raw/` are historical source material.
Artifacts under `legacy/artifacts/` remain runnable only because validators and
tests still exercise them.

Do not:

- move `_v1` receipt schemas back into root `schemas/`
- treat a chaos wave note as active recovery law
- claim that a receipt proves repair or root cause
- hand-edit examples without running the package tests

Validation:

```bash
python -m pytest mechanics/runtime-repair/legacy/artifacts/tests
```
