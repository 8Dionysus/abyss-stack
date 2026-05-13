# AGENTS.md

Applies to `mechanics/inference-pilots/`.

This package owns the route shape for bounded local inference pilots,
benchmarks, model profiles, and trial evidence.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Stable operator wrappers such as `scripts/aoa-llamacpp-pilot`,
`scripts/aoa-qwen-run`, and `scripts/aoa-local-ai-trials` stay at the root
command surface. Active implementations belong under package parts; preserved
compatibility runners belong under `legacy/trials/artifacts/scripts/` and
should be reached through thin part-local bridges.

Do not promote a model, tuning overlay, or worker path without recorded evidence
and a runtime check.

Validation:

```bash
python scripts/validate_stack.py
python -m pytest mechanics/inference-pilots/parts/local-trials/tests/test_aoa_local_ai_trials.py -q
python -m py_compile mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_check.py mechanics/inference-pilots/parts/local-trials/aoa_local_ai_trials.py mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py mechanics/inference-pilots/parts/promotion-loop/aoa_runtime_bench_index.py
bash -n scripts/aoa-qwen-bench scripts/aoa-long-horizon-pilot scripts/aoa-bounded-autonomy-pilot
bash -n mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_bench.sh mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_long_horizon_pilot.sh mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_bounded_autonomy_pilot.sh
python -m py_compile mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-local-ai-trials mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w5-pilot mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w6-pilot
```

Agon dry-run kernels now route through `mechanics/agon-runtime/`.
Archived pilot surfaces route through `mechanics/inference-pilots/legacy/`
and `PROVENANCE.md`.
