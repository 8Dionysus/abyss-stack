# AGENTS.md

Applies to `mechanics/experience-runtime/legacy/`.

This directory preserves old flat experience runtime seed surfaces after the
mechanics topology refactor.

Use `../README.md` and `../PROVENANCE.md` before treating any legacy file as
evidence. Raw docs are historical source material. Artifact schemas/examples
remain contract-tested, but they are still contained legacy surfaces.

Do not:

- rename old wave tests without updating the index and pytest route
- move `_v1` schemas or examples back to root folders
- promote seed docs into active runtime law without a distillation note
- blur stack runtime contracts with AoA or ToS meaning authority

Validation:

```bash
python -m pytest mechanics/experience-runtime/legacy/artifacts/tests
```
