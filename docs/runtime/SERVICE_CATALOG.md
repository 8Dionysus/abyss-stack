# SERVICE CATALOG

This file maps the first migrated runtime modules to their intended services.

## Profile posture

- `substrate` owns the conservative working AbyssOS service base:
  `10-storage.yml` plus `20-orchestration.yml`.
- `local-worker` owns the canonical `llama.cpp` plus `langchain-api` worker
  layer and is meant to compose over `substrate`.
- `fallback-gateway` owns retained Ollama plus LiteLLM fallback/control
  surfaces; it is explicit and not part of the default substrate.
- `core` remains a compatibility bundle for storage, orchestration, and
  `llama.cpp` basics; it is not the default substrate law.
- `agentic`, `intel`, federation, tools, curation, and observability profiles
  stay explicit runtime choices.

## `10-storage.yml`

- `postgres` — transactional state
- `redis` — cache, queue, and ephemeral coordination
- `qdrant` — vector store
- `neo4j` — graph store

## `20-orchestration.yml`

- `n8n` — workflow orchestration
- `n8n-task-runners` — external n8n JavaScript/Python task runner sidecar, version-matched to n8n and connected through the internal broker on `5679`

## `30-local-inference.yml`

- `ollama` — retained local control and rollback serving surface for the
  fallback gateway lane and fallback embeddings

## `31-intel-inference.yml`

- `ovms` — current reviewed Intel and OpenVINO oriented serving surface in promoted presets; the current landed use is embeddings
- OVMS, OpenVINO, and future OpenVINO GenAI lanes may host other model classes through separate reviewed profile, preset, machine-fit, or rollout changes
- any migration from OVMS/OpenVINO serving to OpenVINO GenAI, or promotion of a non-embedding Intel-served lane, is a separate reviewed stack change

## `32-llamacpp-inference.yml`

- `llama-cpp` — canonical OpenAI-compatible GGUF serving surface for bounded local-worker flows
- reuses a resolved local GGUF model file and backs the canonical local text worker path; the current reviewed default model label remains Qwen, but the model choice is host-fit and env-overridable

## `40-llm-gateway.yml`

- `litellm` — retained model gateway and routing facade for the explicit
  `fallback-gateway` profile

## `41-agent-api.yml`

- `langchain-api` — canonical agent-facing runtime API on `5403`
- resolves its chat target through a generic runtime-chat seam, with the reviewed default still pointing at `llama.cpp`
- default embeddings path — disabled unless an explicit embeddings backend is layered in
- may consume a public-safe return policy file and emit runtime return events
- now also exposes opt-in `POST /run/federated` for live advisory consumption of `route-api` playbook and memo seams
- returns the normal model answer plus a redacted `advisory_trace` when the federated path is enabled
- future gateway cache-lane status contract is documented in `mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md`; it is a status-only runtime artifact and does not add new HTTP endpoints in this contract surface
- future runtime usage and budget readout is documented in `mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md`; it remains a bounded runtime artifact, not routing, billing, or quality authority

## `42-agent-api-intel.yml`

- `langchain-api` overlay — switches the current reviewed embeddings path to OVMS
- adds explicit OVMS runtime dependency for Intel-aware profiles
- does not silently promote an Intel-served text lane, but it can support one when the generic runtime-chat seam is explicitly repointed and separately reviewed

## `44-llamacpp-agent-sidecar.yml`

- `langchain-api-llamacpp` — bounded alternate `llama.cpp` API surface used for explicit benchmark and promotion work
- keeps the current reviewed OVMS embeddings lane in place for the Intel-aware posture while leaving broader Intel-serving work to separate reviewed changes
- keeps `POST /run/federated` enabled on the sidecar path so governed execution can consume advisory playbook and memo seams while remaining fail-closed
- joins the shared `abyss_default` runtime network so the advisory `route-api` remains reachable by service name even though the sidecar runs in its own compose project

## Execution layer

- `LangGraph` is now the adopted bounded execution layer for long-horizon and autonomy-focused local-worker flows
- it remains a CLI-side execution surface rather than a long-running network service
- the original `aoa-langgraph-pilot` remains useful as the staged-edit comparison and fixture surface
- `aoa-governed-run` is the first fail-closed governed mutation lane, gated by `aoa-status --autonomy --json` and scoped to `abyss-stack`
- the same lane now exposes canary request materialization, promotion summaries, and operator triage through `aoa-governed-run status`
- governed execution still consumes playbook and memo context through advisory seams; it does not turn `route-api` into an execution service
- `mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md` preserves `aoa-doctor` as readiness-only while future local ops readout stays a separate bounded status surface

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

## `52-tos-graph.yml`

- `tos-graph` — route-first localhost helper for Tree of Sophia graph curation on `5410`
- reads canonical ToS source files from the mounted `AOA_TOS_ROOT`
- keeps Neo4j in projection-only posture and does not treat mirrored `tos-source` advisory surfaces as canonical edit input
- current first slice exposes a route-first localhost UI, health and route/tree/graph inspection APIs, and route-scoped Neo4j sync while writeback remains deferred

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
- tos-graph
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
