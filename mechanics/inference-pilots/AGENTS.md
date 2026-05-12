# AGENTS.md

Applies to `mechanics/inference-pilots/`.

This package owns the route shape for bounded local inference pilots,
benchmarks, model profiles, and trial evidence.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not promote a model, tuning overlay, or worker path without recorded evidence
and a runtime check.

Validation:

```bash
python scripts/validate_stack.py
python -m pytest mechanics/inference-pilots/parts/local-trials/tests/test_aoa_local_ai_trials.py -q
bash -n scripts/aoa-llamacpp-pilot scripts/aoa-qwen-run scripts/aoa-qwen-bench scripts/aoa-local-ai-trials scripts/aoa-long-horizon-pilot scripts/aoa-bounded-autonomy-pilot
python -m py_compile mechanics/inference-pilots/legacy/artifacts/scripts/aoa-w5-pilot mechanics/inference-pilots/legacy/artifacts/scripts/aoa-w6-pilot
```

Agon dry-run kernels now route through `mechanics/agon-runtime/`.
Preserved W5/W6 pilot surfaces route through `mechanics/inference-pilots/legacy/`
and `PROVENANCE.md`.
