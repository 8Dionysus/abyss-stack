# AGENTS.md

Applies to `mechanics/inference-pilots/legacy/`.

This directory preserves archived pilot docs, trial runner scripts, and old
local trial baseline notes after the mechanics topology refactor.

Use `../README.md` and `../PROVENANCE.md` before treating a legacy wave artifact
as current evidence. Trial docs and runners live under `legacy/trials/`.
Runner scripts under `legacy/trials/artifacts/scripts/` remain executable only
through current bridge commands and tests.

Do not:

- move W5/W6 docs back into root `docs/`
- make W5/W6 summaries operator health truth
- make the W0-W4 baseline a first-run requirement
- claim trial-proven evidence as live availability
- widen pilot scripts into autonomous mutation authority

Validation:

```bash
scripts/aoa-long-horizon-pilot --help
scripts/aoa-bounded-autonomy-pilot --help
bash -n scripts/aoa-long-horizon-pilot scripts/aoa-bounded-autonomy-pilot
python -m py_compile mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-local-ai-trials mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w5-pilot mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w6-pilot
```
