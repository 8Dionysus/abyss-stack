# Inference Pilots Parts

| Part | Route | Current source surfaces |
|---|---|---|
| llama.cpp pilot | `parts/llamacpp-pilot/` | `mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md`, `scripts/aoa-llamacpp-pilot`, `parts/llamacpp-pilot/aoa_llamacpp_pilot.py`, `compose/modules/32-llamacpp-inference.yml` |
| Qwen routes | `parts/qwen-routes/` | `scripts/aoa-qwen-run`, `scripts/aoa-qwen-check`, `scripts/aoa-qwen-bench`, `parts/qwen-routes/aoa_qwen_run.py`, `parts/qwen-routes/aoa_qwen_check.py`, `parts/qwen-routes/aoa_qwen_bench.sh`, `mechanics/machine-fit/parts/inference-tuning/docs/model-cards/` |
| LangGraph pilot | `parts/langgraph-pilot/` | `mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md`, `scripts/aoa-langgraph-pilot`, `parts/langgraph-pilot/aoa_langgraph_pilot.py` |
| Local trials | `parts/local-trials/` | `mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md`, `mechanics/inference-pilots/parts/local-trials/docs/RUNTIME_BENCH_POLICY.md`, `scripts/aoa-local-ai-trials`, `parts/local-trials/aoa_local_ai_trials.py`, runtime benchmark schema, example, and focused test |
| Promotion loop | `parts/promotion-loop/` | `mechanics/inference-pilots/parts/promotion-loop/docs/RUNTIME_WINNER_PROMOTION_LOOP.md`, `scripts/aoa-runtime-bench-index`, `parts/promotion-loop/aoa_runtime_bench_index.py` |
| Preserved pilot surfaces | `parts/preserved-pilot-surfaces/` | `legacy/raw/W5_PILOT.md`, `legacy/raw/W6_PILOT.md`, `legacy/artifacts/scripts/aoa-w5-pilot`, `legacy/artifacts/scripts/aoa-w6-pilot` |
| Quiet bridge commands | `parts/quiet-bridge-commands/` | `scripts/aoa-long-horizon-pilot`, `scripts/aoa-bounded-autonomy-pilot`, `parts/quiet-bridge-commands/aoa_long_horizon_pilot.sh`, `parts/quiet-bridge-commands/aoa_bounded_autonomy_pilot.sh` |
| Agon dry-run handoff | `parts/agon-dry-run-handoff/` | `mechanics/agon-runtime/README.md` |

Future moves must keep root commands quiet, package-local provenance explicit,
and validator paths aligned in the same change.
