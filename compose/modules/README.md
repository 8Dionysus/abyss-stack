# compose modules

Modules are the atomic compose pieces. They do not decide by themselves whether
a service belongs to the default AbyssOS substrate.

## Module Rings

| Module | Ring | Normal route |
|---|---|---|
| `10-storage.yml` | substrate | `substrate` |
| `20-orchestration.yml` | workflow automation | `workflows` |
| `30-local-inference.yml` | retained fallback | `fallback-gateway` |
| `31-intel-inference.yml` | worker accelerator | `intel-worker` |
| `32-llamacpp-inference.yml` | local worker | `local-worker`, `intel-worker` |
| `40-llm-gateway.yml` | retained fallback | `fallback-gateway` |
| `41-agent-api.yml` | local worker | `local-worker`, `intel-worker` |
| `42-agent-api-intel.yml` | worker accelerator overlay | `intel-worker` |
| `43-federation-router.yml` | advisory seam | `federation` |
| `44-llamacpp-agent-sidecar.yml` | pilot sidecar | `aoa-llamacpp-pilot` or explicit extra compose |
| `45-rerank-api.yml` | retrieval reranker | `reranking` |
| `46-rag-api.yml` | RAG orchestration | `rag` |
| `50-speech.yml` | helper | `tools` |
| `51-browser-tools.yml` | helper | `tools` |
| `52-tos-graph.yml` | projection helper | `curation` |
| `53-babelvox-tts.yml` | experimental speech helper | `speech-fast-experimental` |
| `60-monitoring.yml` | visibility | `observability` |

## Stop Line

Do not add a module to `substrate` because it is useful. `substrate` is the
storage base. Workflow automation, workers, fallback control paths, advisory
seams, helpers, projections, and dashboards layer on top through explicit
profiles or presets.
