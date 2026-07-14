# Service Optimization Research - 2026-05-16

This note records the current abyss-stack service selection and tuning posture
for the Intel Core Ultra 9 285H workstation. It is an operator research packet,
not a promotion of every selected service to always-resident status.

## July 2026 OVMS Correction

Later cgroup v2 evidence narrowed the May preference for container-level hard
caps. The selected OVMS embedding lane reached its private memory and swap
boundaries while the host still had substantial `MemAvailable`, producing
avoidable local reclaim. Its thin-host overlay now keeps CPU/thread tuning and
`mem_reservation` protection but leaves `memory.max` and `memory.swap.max`
unbounded; owner health, config reload, embedding parity, and rollback remain
the release controls. The May storage and optional-service conclusions below
remain historical context and require their own measured canaries before any
equivalent change.

## Local Evidence

- Live stack service set at inspection time: storage (`postgres`, `redis`,
  `qdrant`, `neo4j`), Intel worker (`llama-cpp`, `ovms`, `langchain-api`),
  federation/rerank (`route-api`, `rerank-api`), tools (`qwen-tts`,
  `tts-router`, `docs-api`, `aoa-browser`), and observability (`prometheus`,
  `grafana`, `alertmanager`, `cadvisor`).
- `n8n` and `n8n-task-runners` were not running in the live stack. They remain
  opt-in through the `workflows` profile.
- Before the staged unit update, live storage containers had no compose memory
  or CPU caps (`MemLimit=0`, `NanoCpus=0`) even though
  `compose/tuning/storage.intel-285h.resource-guard.yml` existed.
- The user unit now stages this overlay set for the next controlled restart:
  `storage.intel-285h.resource-guard`, `intel-worker.thin-host`,
  `federation.thin-host`, `llamacpp.gemma4-e2b.intel-285h.vulkan`,
  `observability.thin-host`, and `tools.thin-host`.
- Existing running storage containers are intentionally unchanged until
  `podman-compose-abyss.service` is restarted or reloaded.
- The RAG preparation pass adds `rag-api` as a lightweight orchestration service
  over existing Qdrant, Neo4j, OVMS embeddings, rerank, route, and langchain
  lanes. It is bounded by `rag.thin-host` and does not make n8n, Dagster, or
  Temporal resident by default.
- `scripts/aoa-status --resource-guards` is the lightweight check for this
  staged-vs-live boundary.
- `scripts/aoa-apply-resource-guards` is the controlled apply route; it captures
  pre/post status and refuses to reload or restart while the host game guard is
  active unless the operator passes `--force`. It also writes pre/post
  `podman stats --no-stream` and memory/PSI snapshots under
  `${AOA_STACK_ROOT}/Logs/resource-guards/latest/`, captures pre/post
  service-selection status, records protected TTS/dictation/stack user-unit
  state, and fails if service selection or protected units degrade after apply.

## Decisions

### Storage stays resident, but bounded

`postgres`, `redis`, `qdrant`, and `neo4j` are substrate state services, so the
right move is resource guarding rather than disabling them. The staged storage
overlay caps container memory/CPU and also sets service-native limits:

- Neo4j: heap, page cache, and `ExitOnOutOfMemoryError`.
- Redis: `maxmemory` plus `noeviction`.
- Postgres: `shared_buffers`, `work_mem`, `maintenance_work_mem`, and connection
  count.
- Qdrant: container limit plus telemetry-disabled startup.

This matches upstream guidance: Neo4j expects explicit Docker memory
configuration for production-like use, Redis recommends `maxmemory`, PostgreSQL
documents `shared_buffers` as a bounded shared memory setting, and Qdrant
explicitly says on-disk vectors can still report high RSS because disk data is
cached or preloaded.

### Observability stays explicit and thin

Prometheus, Grafana, Alertmanager, cAdvisor, Loki, and Alloy are useful when
diagnosing the machine, but they should not be unconstrained background noise.
The `observability.thin-host` overlay keeps the services selected only when the
profile includes observability, shortens Prometheus and Loki retention, sets
retention size, caps dashboard memory, lowers cAdvisor sampling cadence, and
keeps log ingestion internal-only.

This aligns with Prometheus' storage retention flags, Prometheus'
container-aware Go memory limit behavior, cAdvisor's documented housekeeping
intervals, Loki's current single-binary plus TSDB/filesystem guidance, and
Grafana Alloy's journal-source and file-source ingestion paths.

### Workflows stay opt-in

n8n should not be resident just because the stack knows how to run it. When
enabled, the task-runner path should use external runners, explicit memory
ceilings, low concurrency, and bounded payload size. n8n's own docs recommend
external task runners for production-style isolation, one runner sidecar per
queue worker, matching n8n/runner versions, and an auto-shutdown timeout for idle
runners.

### One primary text lane

For current local agent work, keep one primary text lane: Gemma 4 E2B through
`llama.cpp`/Vulkan as an explicit overlay. Keep OVMS on the embeddings lane.
Do not pursue Gemma 4 on OVMS here. llama.cpp exposes the relevant tuning knobs
for this machine class: context size, logical batch, physical ubatch, fit target,
and cache controls.

### Worker and federation facades are bounded separately

`ovms`, `langchain-api`, and `route-api` are not storage services, so they should
not be hidden inside the storage guard. The separate `intel-worker.thin-host`
and `federation.thin-host` overlays bound those promoted facades while keeping
their profile ownership visible.

### Forum and field evidence

The practical warning from user reports is consistent with upstream docs: high
container RSS is not automatically a leak, especially for mmap/vector stores and
caches. A Qdrant desktop-memory issue reports paging pain even with `on_disk`,
while self-hosting operators warn that periodic blind restarts are not a tuning
strategy. For this machine, prefer container-level caps, service-native limits,
PSI/zram evidence, and controlled restarts over killing services.

## Sources

- n8n task runners: https://docs.n8n.io/hosting/configuration/task-runners/
- n8n task runner environment variables:
  https://docs.n8n.io/hosting/configuration/environment-variables/task-runners/
- Qdrant optimizer and memmap threshold:
  https://qdrant.tech/documentation/operations/optimizer/
- Qdrant memory FAQ:
  https://qdrant.tech/documentation/faq/database-optimization/
- Qdrant desktop memory issue:
  https://github.com/qdrant/qdrant/issues/5184
- Neo4j Docker configuration:
  https://neo4j.com/docs/operations-manual/current/docker/configuration/
- Neo4j Docker memory recommendation:
  https://neo4j.com/docs/operations-manual/current/docker/operations/
- Redis memory optimization:
  https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/
- Redis eviction and `maxmemory`:
  https://redis.io/docs/latest/develop/reference/eviction/
- PostgreSQL resource consumption:
  https://www.postgresql.org/docs/current/runtime-config-resource.html
- Prometheus storage:
  https://prometheus.io/docs/prometheus/latest/storage/
- Prometheus command-line flags:
  https://prometheus.io/docs/prometheus/latest/command-line/prometheus/
- Loki Docker install:
  https://grafana.com/docs/loki/latest/setup/install/docker/
- Loki TSDB and filesystem storage:
  https://grafana.com/docs/loki/latest/configure/storage/
- Grafana Alloy Loki journal source:
  https://grafana.com/docs/alloy/latest/reference/components/loki.source.journal/
- Grafana Alloy Loki file source:
  https://grafana.com/docs/alloy/latest/reference/components/loki.source.file/
- cAdvisor runtime options:
  https://github.com/google/cadvisor/blob/master/docs/runtime_options.md
- llama.cpp server options:
  https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Self-hosting operator discussion on memory and restarts:
  https://www.reddit.com/r/selfhosted/comments/1jneagx/psa_check_your_docker_memory_usage_restart/

## Next Verification Window

When the machine is idle enough for a controlled stack restart:

1. Run `scripts/aoa-apply-resource-guards --dry-run` and confirm host load gates
   allow the apply action.
2. Run `scripts/aoa-apply-resource-guards` for the default recreate apply. Use
   `--method reload` only for a lighter best-effort path, or add
   `--method restart` for a full down/up window.
3. Run `scripts/aoa-status --resource-guards` and confirm the status is
   `applied`.
4. Confirm `post-service-selection.json` reports `ok` and
   `post-protected-units.txt` shows the protected units active.
5. Compare `pre-podman-stats.txt`, `post-podman-stats.txt`,
   `pre-memory.txt`, and `post-memory.txt` under
   `${AOA_STACK_ROOT}/Logs/resource-guards/latest/`.
6. If OVMS, `langchain-api`, or `route-api` still show unhealthy swap behavior
   under real load, tune the new worker/federation overlay values instead of
   widening the storage overlay.
