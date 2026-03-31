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

- `ollama` — retained local control and rollback serving surface for Qwen chat and fallback embeddings

## `31-intel-inference.yml`

- `ovms` — current Intel and OpenVINO oriented model serving surface for embeddings
- any migration from OVMS/OpenVINO serving to OpenVINO GenAI is a separate reviewed stack change

## `32-llamacpp-inference.yml`

- `llama-cpp` — promoted OpenAI-compatible GGUF serving surface for bounded local-worker flows
- reuses a resolved local GGUF model file and now backs the preferred local Qwen worker path on `5403`
- keeps Ollama in place as the control and rollback path

## `40-llm-gateway.yml`

- `litellm` — model gateway and routing facade

## `41-agent-api.yml`

- `langchain-api` — base control-path agent-facing runtime API on `5401`
- default embeddings path — Ollama-first
- may consume a public-safe return policy file and emit runtime return events
- now also exposes opt-in `POST /run/federated` for live advisory consumption of `route-api` playbook and memo seams
- returns the normal model answer plus a redacted `advisory_trace` when the federated path is enabled

## `42-agent-api-intel.yml`

- `langchain-api` overlay — switches embeddings path to OVMS
- adds explicit OVMS runtime dependency for Intel-aware profiles

## `44-llamacpp-agent-sidecar.yml`

- `langchain-api-llamacpp` — promoted bounded local-worker API bound to a `llama.cpp` backend on `5403`
- is the preferred local Qwen worker path for the current promoted `W5/W6` substrate
- preserves the base `langchain-api` service and `5401` path as the control and rollback surface
- keeps embeddings on OVMS for the current Intel-aware posture

## Execution layer

- `LangGraph` is now the adopted bounded execution layer for the `W5` and `W6` local-worker flows
- it remains a CLI-side execution surface rather than a long-running network service
- the original `aoa-langgraph-pilot` remains useful as the W4-shaped comparison and fixture surface
- `aoa-governed-run` is the first fail-closed governed mutation lane, gated by `aoa-status --autonomy --json` and scoped to `abyss-stack`
- governed execution still consumes playbook and memo context through advisory seams; it does not turn `route-api` into an execution service

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
