# Inference Pilots Parts

| Part | Route | Current source surfaces |
|---|---|---|
| llama.cpp pilot | `parts/llamacpp-pilot/` | `docs/LLAMACPP_PILOT.md`, `scripts/aoa-llamacpp-pilot`, `compose/modules/32-llamacpp-inference.yml` |
| Qwen routes | `parts/qwen-routes/` | `scripts/aoa-qwen-run`, `scripts/aoa-qwen-check`, `scripts/aoa-qwen-bench`, `docs/model-cards/` |
| LangGraph pilot | `parts/langgraph-pilot/` | `docs/LANGGRAPH_PILOT.md`, `scripts/aoa-langgraph-pilot` |
| Local trials | `parts/local-trials/` | `docs/LOCAL_AI_TRIALS.md`, `docs/RUNTIME_BENCH_POLICY.md`, `scripts/aoa-local-ai-trials`, runtime benchmark schema, example, and focused test |
| Promotion loop | `parts/promotion-loop/` | `docs/RUNTIME_WINNER_PROMOTION_LOOP.md`, `scripts/aoa-runtime-bench-index` |
| Preserved wave surfaces | `parts/preserved-wave-surfaces/` | `legacy/raw/W5_PILOT.md`, `legacy/raw/W6_PILOT.md`, `legacy/artifacts/scripts/aoa-w5-pilot`, `legacy/artifacts/scripts/aoa-w6-pilot` |
| Quiet bridge commands | `parts/quiet-bridge-commands/` | `scripts/aoa-long-horizon-pilot`, `scripts/aoa-bounded-autonomy-pilot` |
| Agon dry-run handoff | `parts/agon-dry-run-handoff/` | `mechanics/agon-runtime/README.md` |

Future moves must keep root commands quiet, package-local provenance explicit,
and validator paths aligned in the same change.
