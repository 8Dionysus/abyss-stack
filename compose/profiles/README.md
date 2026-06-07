# compose profiles

Profiles are named runtime selections. They keep service selection visible
without turning every module into the default AbyssOS substrate.

## Rings

| Profile | Ring | Role |
|---|---|---|
| `substrate` | base | storage only; the source-owned default |
| `workflows` | optional workflow automation | n8n plus its storage dependency |
| `local-worker` | worker | canonical `llama.cpp` plus `langchain-api` path |
| `intel-worker` | worker accelerator | canonical local worker plus reviewed OVMS embeddings seam |
| `fallback-gateway` | retained fallback | Ollama plus LiteLLM control and rollback path |
| `core` | compatibility | storage and `llama.cpp` basics for older habits |
| `agentic` | compatibility | older name for storage plus canonical local-worker API |
| `intel` | compatibility | older name for storage plus reviewed Intel worker seam |
| `federation` | advisory seam | localhost federation and retrieval reader |
| `reranking` | retrieval reranker | opt-in OpenVINO Qwen3 rerank API |
| `rag` | RAG orchestration | source-linked ingest/retrieve/answer API over existing stores and model lanes |
| `speech-fast-experimental` | experimental speech | opt-in BabelVox/OpenVINO TTS lane |
| `curation` | projection helper | ToS graph helper plus storage substrate |
| `tools` | helper | speech and browser-like helper services |
| `observability` | visibility | monitoring, dashboards, LogQL storage, and log ingestion |

`44-llamacpp-agent-sidecar.yml` intentionally stays outside this directory's
profiles. It is a pilot sidecar activated by the inference-pilot route or by an
explicit extra compose overlay.

## Rule

If a module is runnable as a normal operator selection, give it a role-named
profile. If a module is a pilot sidecar or one-off overlay, keep it out of
profiles and route it through the owning mechanic.

Current presets should compose `substrate` plus `local-worker` or
`intel-worker` directly. The broad `agentic` and `intel` profiles stay runnable
for compatibility, but they should not become the hidden base for new presets.
`workflows` stays opt-in until an explicit operator or source decision promotes
n8n into a common route.
`reranking` likewise stays opt-in: it exposes the reviewed host Qwen3 OpenVINO
reranker through a stack service without making rerank residency part of every
Intel worker run.
`rag` is selected only when source-linked ingestion, retrieval, answer, and
agentic trace APIs are needed. It depends on storage, the Intel embedding lane,
federation advisory surfaces, reranking, and the canonical `langchain-api`; it
does not make n8n, Dagster, or Temporal resident.
`speech-fast-experimental` also stays opt-in: it exposes the BabelVox/OpenVINO
TTS experiment as a bounded stack service without replacing the protected host
warm TTS route or the normal `tools` speech module.
`observability` includes metrics and logs together: Prometheus/PromQL,
Alertmanager, Grafana, cAdvisor, Loki, and Alloy. Loki and Alloy stay
internal-only and are reached through Grafana or internal probes, not host
ports.
