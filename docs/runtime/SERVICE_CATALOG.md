# SERVICE CATALOG

This file maps the first migrated runtime modules to their intended services.

## Profile posture

- `substrate` owns the conservative working AbyssOS service base:
  `10-storage.yml`.
- `workflows` owns optional n8n workflow automation:
  `10-storage.yml` plus `20-orchestration.yml`.
- `local-worker` owns the canonical `llama.cpp` plus `langchain-api` worker
  layer and is meant to compose over `substrate`.
- `fallback-gateway` owns retained Ollama plus LiteLLM fallback/control
  surfaces; it is explicit and not part of the default substrate.
- `core` remains a compatibility bundle for storage and `llama.cpp` basics; it
  is not the default substrate law.
- `intel-worker` owns the reviewed OVMS embeddings seam over the canonical
  local worker path.
- `agentic` and `intel` remain runnable compatibility profiles; current named
  presets compose `substrate` plus worker layers directly.
- `workflows`, federation, tools, curation, and observability profiles stay
  explicit runtime choices.
- `reranking` is an explicit add-on for the OpenVINO Qwen3 reranker API; it is
  not part of the default Intel worker lane until separately promoted.
- `rag` is the first RAG orchestration profile. It layers a lightweight
  localhost API over existing storage, embedding, rerank, route, and text lanes
  rather than adding another vector DB or making n8n the retrieval brain.
- Service selection and optimization rules live in
  [`SERVICE_SELECTION.md`](SERVICE_SELECTION.md). In short, `intel-federation`
  is the lean Intel-aware agent shape, while `intel-full` intentionally adds
  helper tools and observability and should not be mistaken for the minimum
  resident runtime.

## `10-storage.yml`

- `postgres` — transactional state
- `redis` — cache, queue, and ephemeral coordination
- `qdrant` — vector store
- `neo4j` — graph store

## `20-orchestration.yml`

- `n8n` — optional workflow automation
- `n8n-task-runners` — external n8n JavaScript/Python task runner sidecar, version-matched to n8n and connected through the internal broker on `5679`

## `30-local-inference.yml`

- `ollama` — retained local control and rollback serving surface for the
  fallback gateway lane and fallback embeddings

## `31-intel-inference.yml`

- `ovms` — current reviewed Intel/OpenVINO embeddings workload selected by the
  module but owned by rootless systemd rather than Compose
- `abyss-ovms.socket` and `abyss-ovms-unix.socket` activate an idle proxy;
  `abyss-ovms.container` is the Quadlet source for the full container lifecycle
- port `8200` remains loopback-only; `langchain-api` uses the private Unix
  socket, and periodic monitoring must not open either activation socket
- `aoa-up` links the owner units and retires a same-project legacy Compose
  `ovms` container before opening the sockets; the client mounts the containing
  runtime directory read-only so socket recreation remains visible without
  recreating `langchain-api`, while the client cannot mutate admission state
- the client timeout is 600 seconds to cover the bounded admission wait and
  digest image pull/model-start window on a cold first request
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
- emits a redacted runtime trace for `/run`, `/run/federated`, and `POST /langgraph/smoke`, storing thread/checkpoint/trace inventory under `${AOA_STACK_ROOT}/Logs/langgraph-inventory` and best-effort OTLP spans through Alloy/Tempo
- exposes bounded read routes for that inventory at `/langgraph/inventory`, `/threads`, `/threads/{thread_id}/checkpoints`, `/traces`, and `/traces/{trace_id}` without storing raw prompt, answer, or advisory payload text
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
- exposes `GET /observability/datasources` as a read-only Grafana datasource
  inventory derived from provisioned datasource YAML, with secrets and
  `secureJsonData` omitted
- remains an advisory facade; it does not execute the route itself, while `langchain-api` is now the first live consumer of those mirrored seams

## `45-rerank-api.yml`

- `rerank-api` — localhost-only OpenVINO Qwen3 reranker API on `5405`
- wraps the host-validated CausalLM-style Qwen3 reranker scorer through
  `POST /v3/rerank` and `POST /rerank`
- keeps `GET /health` lightweight and loads the model lazily on the first
  rerank request
- unloads the model after an idle window by default
  (`AOA_RERANK_IDLE_UNLOAD_SEC=900`) so occasional reranking does not keep a
  multi-GB OpenVINO model resident forever; `POST /admin/unload` is available
  for explicit localhost memory relief
- exposes `POST /admin/memory-relief` for automated owner-gated relief; the
  endpoint atomically refuses inflight work, drains new requests before a
  process exit, commits the action receipt before releasing the model, and
  deduplicates an exact action ID across container restarts
- exits after idle unload by default (`AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD=true`)
  so Podman restarts a clean lightweight API process and returns allocator-held
  memory to the host
- separately exits after successful owner relief by default
  (`AOA_RERANK_EXIT_AFTER_MEMORY_RELIEF=true`) and keeps at most 32 atomic
  action receipts under owner state in `Logs/rerank-api`
- uses `/srv/abyss-machine/cache/ai` for the model and OpenVINO cache by
  default, not the limited system root

## `46-rag-api.yml`

- `rag-api` — localhost-only RAG orchestration API on `5406`
- consumes `Configs/rag/sources.json`, `agentic-graph.v1.json`, and
  `dag-jobs.v1.json` as public-safe runtime manifests
- uses Qdrant for source-linked chunk retrieval, OVMS embeddings through
  `langchain-api`, optional `rerank-api` scoring, `route-api` advisory surfaces,
  and `langchain-api` answer generation
- exposes `GET /sources`, `GET /dag/jobs`, `GET /agentic-rag/graph`,
  `GET /semantic-inventory`, `POST /ingest/source`, `POST /retrieve`,
  `POST /answer`, and `POST /agentic-rag/run`
- `GET /semantic-inventory` is a bounded memory-space read route for Postgres
  schema/freshness, Neo4j label/relationship/freshness, RAG sources, and
  agentic graph shape; it does not return rows, graph properties, source
  documents, or credentials
- keeps n8n, Dagster, and Temporal out of the resident RAG path; those remain
  explicit DAG/integration lanes until a later promotion proves they should be
  always-on

## `50-speech.yml`

- `qwen-tts` — local speech generation
- `tts-router` — speech routing and voice selection facade

## `51-browser-tools.yml`

- `docs-api` — internal docs helper surface
- `aoa-browser` — internal browser automation helper

## `52-tos-graph.yml`

- `tos-graph` — corpus and philosophy graph localhost helper for Tree of Sophia graph curation on `5410`
- reads the ToS-owned whole-corpus index and materialized philosophy graph projection from the mounted `AOA_TOS_ROOT`
- keeps Neo4j in projection-only posture and does not treat mirrored `tos-source` advisory surfaces as canonical edit input
- current slice exposes a bundled WebGL localhost workbench, health, `/api/corpus/*`, `/api/philosophy/*`, and corpus/philosophy Neo4j projection sync while writeback remains absent
- operator shortcut: `scripts/tos-up` starts the curation profile, waits for the helper, and opens the local workbench when possible; `scripts/aoa-tos-graph` is the explicit stack command behind it

## `53-babelvox-tts.yml`

- `babelvox-tts` — opt-in BabelVox/OpenVINO TTS API on `5102`
- mounts the host-owned TTS Hugging Face cache under `/srv/abyss-machine/cache/ai/tts` so offline model lookup does not spill into the system root
- keeps `GET /health` lightweight and loads BabelVox lazily on the first synthesis request
- unloads after an idle window by default (`AOA_BABELVOX_TTS_IDLE_UNLOAD_SEC=900`) and can exit after unload so Podman returns allocator-held memory to the host
- is experimental and must not replace the protected host warm TTS route without separate hot-path latency and memory evidence

## `60-monitoring.yml`

- `prometheus` — metrics collection
- `grafana` — dashboards
- `alertmanager` — alert routing
- `cadvisor` — container metrics
- `loki` — internal-only log storage and LogQL query surface
- `tempo` — localhost-only Tempo trace backend on `3200` with internal OTLP ingest from Alloy
- `alloy` — Grafana Alloy rootless Podman log ingestion into Loki, journald-first with a file-log fallback, plus localhost-only OTLP trace ingest on `4317`/`4318` forwarded to Tempo

## Exposure posture

### Host-facing

Expected localhost-only services may include, depending on selected profiles:
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
- rerank-api
- rag-api
- tos-graph
- qwen-tts
- tts-router
- babelvox-tts
- prometheus
- grafana
- alertmanager
- loki
- alloy

### Internal-only

Expected internal-only services include:
- docs-api
- aoa-browser
- cadvisor
- loki
- alloy

## User-unit orchestration

`systemd/user/managed-units.txt` is the source-managed allowlist for host-local
user units that can be linked from the deployed Configs mirror with
`scripts/aoa-install-systemd --all-user-units`.

The allowlist covers the current working user-service surface: the stack compose
runner, warm dictation and TTS services, the TTS keep-warm timer, the
`gemma4.spark` resident and timers,
nervous capture/index/semantic maintenance, process/storage/topology/doctor
readouts, `ydotoold`, and the AoA receipt watcher path units.

These units are orchestration adapters. They may call host-owned commands such
as `abyss-machine`, but their presence here does not transfer host-layer
implementation authority into `abyss-stack`.

`systemd/system/managed-units.txt` is the separate privileged support allowlist.
It covers the dictation hotkey listener and lightweight machine refresh,
observability, and power-profile timers. Install it with
`pkexec .../aoa-install-systemd --system-units`; the install path writes
root-owned unit files and reloads systemd without restarting or enabling
services.
