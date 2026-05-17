# compose layout

The new stack uses small compose modules, named profiles, and named presets.
Use [modules](modules/README.md) for module rings and
[profiles](profiles/README.md) for profile roles.

## Modules

- `modules/10-storage.yml`
- `modules/20-orchestration.yml`
- `modules/30-local-inference.yml`
- `modules/31-intel-inference.yml`
- `modules/32-llamacpp-inference.yml`
- `modules/40-llm-gateway.yml`
- `modules/41-agent-api.yml`
- `modules/42-agent-api-intel.yml`
- `modules/43-federation-router.yml`
- `modules/44-llamacpp-agent-sidecar.yml`
- `modules/45-rerank-api.yml`
- `modules/46-rag-api.yml`
- `modules/50-speech.yml`
- `modules/51-browser-tools.yml`
- `modules/52-tos-graph.yml`
- `modules/53-babelvox-tts.yml`
- `modules/60-monitoring.yml`

`41-agent-api.yml` may consume a public-safe return policy file from `Configs/agent-api/return-policy.yaml`.

## Profiles

- `profiles/substrate.txt`
- `profiles/workflows.txt`
- `profiles/local-worker.txt`
- `profiles/intel-worker.txt`
- `profiles/fallback-gateway.txt`
- `profiles/core.txt`
- `profiles/agentic.txt`
- `profiles/intel.txt`
- `profiles/federation.txt`
- `profiles/reranking.txt`
- `profiles/rag.txt`
- `profiles/speech-fast-experimental.txt`
- `profiles/curation.txt`
- `profiles/tools.txt`
- `profiles/observability.txt`

A profile is only a list of module filenames in activation order.

`substrate` is the conservative working service base for AbyssOS runtime
bring-up: storage only. `workflows` is the optional n8n workflow automation
layer, including its storage dependency so it can run on its own or compose over
`substrate`. `local-worker` is the canonical `llama.cpp` plus `langchain-api`
worker layer. `intel-worker` is the reviewed OVMS embeddings layer over the
canonical local worker. `fallback-gateway` keeps the retained Ollama plus
LiteLLM control path explicit. `core`, `agentic`, and `intel` remain
compatibility bundles for older operator habits; current presets compose
`substrate` plus worker layers directly and do not include `workflows`.
`reranking` is an explicit add-on for the source-owned OpenVINO Qwen3 reranker
API; keep it opt-in until stack-level rerank usage has its own promotion record.
`rag` is the first lightweight RAG orchestration profile. It layers a localhost
`rag-api` over Qdrant, Neo4j, OVMS embeddings, `rerank-api`, `route-api`, and
`langchain-api` without adding another vector store or making workflow tools
the retrieval brain.
`speech-fast-experimental` is an explicit BabelVox/OpenVINO TTS lane for
Intel speech experiments; keep it opt-in until latency and memory evidence
justify promotion.

## Presets

- `presets/agent-federation.txt`
- `presets/agent-tools.txt`
- `presets/agent-observability.txt`
- `presets/agent-full.txt`
- `presets/intel-federation.txt`
- `presets/intel-tools.txt`
- `presets/intel-observability.txt`
- `presets/intel-full.txt`

A preset is a list of profile names in activation order.

## Runtime and pilot modules

`32-llamacpp-inference.yml` is the canonical local-worker inference module. It
is used by `local-worker`, `intel-worker`, and the compatibility bundles that
preserve older profile names.

`44-llamacpp-agent-sidecar.yml` is separate. It exists for the bounded
`llama.cpp` sidecar pilot and is typically activated through:

- `scripts/aoa-llamacpp-pilot`
- or `AOA_EXTRA_COMPOSE_FILES` when you intentionally want the sidecar path

## Rule

New capability should arrive as:
1. a module
2. optionally a profile inclusion
3. optionally a preset inclusion for a common operating bundle
4. corresponding docs and lifecycle notes

Not as a silent growth of one giant compose file.
