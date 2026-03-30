# SERVICE CATALOG

This file maps the first migrated runtime modules to their intended services.

## `10-storage.yml`

- `postgres` — transactional state
- `redis` — cache, queue, and ephemeral coordination
- `qdrant` — vector store
- `neo4j` — graph store

## `20-orchestration.yml`

- `n8n` — workflow orchestration

## `30-local-inference.yml`

- `ollama` — local LLM and embedding serving

## `31-intel-inference.yml`

- `ovms` — Intel and OpenVINO oriented model serving

## `32-llamacpp-inference.yml`

- `llama-cpp` — optional OpenAI-compatible GGUF serving sidecar for bounded backend-parity work
- reuses a resolved local GGUF model file rather than changing the canonical validated Ollama path

## `40-llm-gateway.yml`

- `litellm` — model gateway and routing facade

## `41-agent-api.yml`

- `langchain-api` — base agent-facing runtime API
- default embeddings path — Ollama-first
- may consume a public-safe return policy file and emit runtime return events
- now also exposes opt-in `POST /run/federated` for live advisory consumption of `route-api` playbook and memo seams
- returns the normal model answer plus a redacted `advisory_trace` when the federated path is enabled

## `42-agent-api-intel.yml`

- `langchain-api` overlay — switches embeddings path to OVMS
- adds explicit OVMS runtime dependency for Intel-aware profiles

## `44-llamacpp-agent-sidecar.yml`

- `langchain-api-llamacpp` — optional sidecar agent API bound to a `llama.cpp` backend on a separate host port
- preserves the canonical `langchain-api` service and `5401` path for honest A/B comparison
- keeps embeddings on OVMS for Intel-aware pilot runs

## `43-federation-router.yml`

- `route-api` — localhost-only federation seam reader for mirrored `aoa-agents` contracts, `aoa-routing advisory routing surfaces`, `aoa-memo` recall surfaces, `aoa-evals` eval selection surfaces, `aoa-playbooks` activation/composition advisory surfaces, `aoa-kag` retrieval/regrounding surfaces, and the source-owned `tos-source` handoff companion
- consumes only runtime-local public-safe mirror data
- exposes thin routing metadata, structured advisory routing, bounded memo inspection, structured eval selection, playbook activation/composition inspection, `/kag/*` retrieval/regrounding inspection, and filesystem-first memo/eval export discovery
- remains an advisory facade; it does not execute the route itself, while `langchain-api` is now the first live consumer of those mirrored seams

## `50-speech.yml`

- `qwen-tts` — local speech generation
- `tts-router` — speech routing and voice selection facade

## `51-browser-tools.yml`

- `docs-api` — internal docs helper surface
- `aoa-browser` — internal browser automation helper

## `60-monitoring.yml`

- `prometheus` — metrics collection
- `grafana` — dashboards
- `alertmanager` — alert routing
- `cadvisor` — container metrics

## Exposure posture

### Host-facing

Expected localhost-only services include:
- postgres
- redis
- qdrant
- neo4j
- n8n
- ollama
- ovms
- llama-cpp
- litellm
- langchain-api
- langchain-api-llamacpp
- route-api
- qwen-tts
- tts-router
- prometheus
- grafana
- alertmanager

### Internal-only

Expected internal-only services include:
- docs-api
- aoa-browser
- cadvisor
