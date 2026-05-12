# AGENTS.md

Applies to `mechanics/inference-pilots/legacy/`.

This directory preserves old W5/W6 pilot docs and runner scripts after the
mechanics topology refactor.

Use `../README.md` and `../PROVENANCE.md` before treating a legacy wave artifact
as current evidence. Raw docs in `legacy/raw/` are historical route material.
Runner scripts under `legacy/artifacts/scripts/` remain executable only through
current bridge commands and tests.

Do not:

- move W5/W6 docs back into root `docs/`
- make W5/W6 summaries operator health truth
- claim trial-proven evidence as live availability
- widen pilot scripts into autonomous mutation authority

Validation:

```bash
scripts/aoa-long-horizon-pilot --help
scripts/aoa-bounded-autonomy-pilot --help
bash -n scripts/aoa-long-horizon-pilot scripts/aoa-bounded-autonomy-pilot
python -m py_compile mechanics/inference-pilots/legacy/artifacts/scripts/aoa-w5-pilot mechanics/inference-pilots/legacy/artifacts/scripts/aoa-w6-pilot
```
