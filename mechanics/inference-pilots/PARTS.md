# Inference Pilots Parts

| Part | Current source surfaces |
|---|---|
| llama.cpp pilot | `docs/LLAMACPP_PILOT.md`, `scripts/aoa-llamacpp-pilot`, `compose/modules/32-llamacpp-inference.yml` |
| Qwen routes | `scripts/aoa-qwen-run`, `scripts/aoa-qwen-check`, `scripts/aoa-qwen-bench`, `docs/model-cards/` |
| LangGraph pilot | `docs/LANGGRAPH_PILOT.md`, `scripts/aoa-langgraph-pilot` |
| Local trials | `docs/LOCAL_AI_TRIALS.md`, `scripts/aoa-local-ai-trials`, `examples/runtime_benchmark.workhorse-local.example.json` |
| Promotion loop | `docs/RUNTIME_WINNER_PROMOTION_LOOP.md`, `scripts/aoa-runtime-bench-index` |
| Preserved wave surfaces | `legacy/raw/W5_PILOT.md`, `legacy/raw/W6_PILOT.md`, `legacy/artifacts/scripts/aoa-w5-pilot`, `legacy/artifacts/scripts/aoa-w6-pilot` |
| Quiet bridge commands | `scripts/aoa-long-horizon-pilot`, `scripts/aoa-bounded-autonomy-pilot` |
| Agon dry-run handoff | `mechanics/agon-runtime/README.md` |

Future moves must keep root commands quiet, package-local provenance explicit,
and validator paths aligned in the same change.
