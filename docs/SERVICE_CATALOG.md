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

- `llama-cpp` — canonical OpenAI-compatible GGUF serving surface for bounded local-worker flows
- reuses a resolved local GGUF model file and backs the canonical local Qwen worker path

## `40-llm-gateway.yml`

- `litellm` — model gateway and routing facade

## `41-agent-api.yml`

- `langchain-api` — canonical agent-facing runtime API on `5403`
- default embeddings path — disabled unless an explicit embeddings backend is layered in
- may consume a public-safe return policy file and emit runtime return events
- now also exposes opt-in `POST /run/federated` for live advisory consumption of `route-api` playbook and memo seams
- returns the normal model answer plus a redacted `advisory_trace` when the federated path is enabled
- future gateway cache-lane status contract is documented in `docs/GATEWAY_CACHE_POLICY.md`; it is a status-only runtime artifact and does not add new HTTP endpoints in this wave
- future runtime usage and budget readout is documented in `docs/USAGE_BUDGET_POLICY.md`; it remains a bounded runtime artifact, not routing, billing, or quality authority

## `42-agent-api-intel.yml`

- `langchain-api` overlay — switches embeddings path to OVMS
- adds explicit OVMS runtime dependency for Intel-aware profiles

## `44-llamacpp-agent-sidecar.yml`

- `langchain-api-llamacpp` — bounded alternate `llama.cpp` API surface used for explicit benchmark and promotion work
- keeps embeddings on OVMS for the current Intel-aware posture
- keeps `POST /run/federated` enabled on the sidecar path so governed execution can consume advisory playbook and memo seams while remaining fail-closed
- joins the shared `abyss_default` runtime network so the advisory `route-api` remains reachable by service name even though the sidecar runs in its own compose project

## Execution layer

- `LangGraph` is now the adopted bounded execution layer for the `W5` and `W6` local-worker flows
- it remains a CLI-side execution surface rather than a long-running network service
- the original `aoa-langgraph-pilot` remains useful as the W4-shaped comparison and fixture surface
- `aoa-governed-run` is the first fail-closed governed mutation lane, gated by `aoa-status --autonomy --json` and scoped to `abyss-stack`
- the same lane now exposes canary request materialization, promotion summaries, and operator triage through `aoa-governed-run status`
- governed execution still consumes playbook and memo context through advisory seams; it does not turn `route-api` into an execution service
- `docs/LOCAL_OPS_DOCTOR_SPLIT.md` preserves `aoa-doctor` as readiness-only while future local ops readout stays a separate bounded status surface

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
- ovms
- llama-cpp
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
