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

## `40-llm-gateway.yml`

- `litellm` — model gateway and routing facade

## `41-agent-api.yml`

- `langchain-api` — base agent-facing runtime API
- default embeddings path — Ollama-first

## `42-agent-api-intel.yml`

- `langchain-api` overlay — switches embeddings path to OVMS
- adds explicit OVMS runtime dependency for Intel-aware profiles

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
- litellm
- langchain-api
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
