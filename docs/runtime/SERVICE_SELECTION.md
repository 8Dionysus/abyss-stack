# SERVICE SELECTION

This note defines how to decide which `abyss-stack` services should be resident,
scheduled, explicit, or optional on a working machine.

It does not replace `SERVICE_CATALOG.md`. The catalog maps modules to services;
this file describes the operating posture for selecting and tuning them.
The machine-readable companion is
[`service-selection-policy.v1.json`](service-selection-policy.v1.json); it keeps
the current service posture, selected runtime shape, and resource-guard mapping
under validator coverage.
The screenshot-derived baseline inventory is
[`service-inventory-2026-05-14.v1.json`](service-inventory-2026-05-14.v1.json);
it records the operator-provided service list that started this optimization
pass and lets validation prove that later policy changes still account for that
baseline.

## Tiers

| Tier | Posture | Services |
|---|---|---|
| Resident interaction | Keep warm when the operator depends on them | host dictation, host TTS, dictation hotkey, `ydotoold`, and the active local text resident |
| Working runtime | Keep up for normal local agent work | `substrate` plus one worker lane and any needed advisory seam |
| Scheduled evidence | Keep as timers, not daemons | nervous capture, derived refresh, index, semantic maintenance, process/storage/topology/doctor readouts |
| Explicit tools | Run only when the current workflow needs them | speech API/router containers, docs/browser helper containers, dashboards, workflow automation |
| Fallback or lab | Keep available but not implicit | Ollama/LiteLLM fallback, alternate llama sidecars, experimental Intel text or GPU overlays |

## Preferred Runtime Shapes

The base runtime remains `substrate`: Postgres, Redis, Qdrant, and Neo4j.

For the current Intel-aware agent path, prefer the lean working shape when
dashboards and helper tools are not part of the task:

```bash
aoa-up --preset intel-federation
```

Use `intel-full` when helper tools and observability are intentionally part of
the work:

```bash
aoa-up --preset intel-full --profile federation
```

That full shape is useful for measurement, dashboards, browser/docs helpers,
and speech-router experiments. It should not be mistaken for the minimum
resident runtime.

## Voice And Speech

Host warm TTS is the interactive operator voice route. Keep
`abyss-tts-server.service` warm when spoken feedback is expected.
Use `abyss-tts-keepwarm.timer` when the host should preserve low-latency speech
readiness over long idle periods; it runs a short synthetic synthesis through
`abyss-machine resource launch` and writes a single cache artifact instead of
restarting, disabling, or replacing the protected TTS service.

The compose `50-speech.yml` services are stack-level speech API/router surfaces.
They are useful when another runtime consumer needs HTTP speech endpoints, but
they should remain an explicit `tools` layer rather than a hidden dependency of
the host TTS contract.

The `speech-fast-experimental` profile exposes `babelvox-tts` as an opt-in
Intel/OpenVINO experiment. Use it for bounded service testing only: current
host evidence shows the cache route is fixed, but NPU/GPU BabelVox cold-path
synthesis is still too slow and too zram-heavy for default interactive speech.
Keep its idle unload/recycle controls enabled unless a later promotion record
proves a better latency/memory tradeoff.

Dictation has the same rule: keep the host dictation server, hotkey listener,
and `ydotoold` warm for interactive use. Do not treat disabling them as service
optimization.

## Model Lanes

Use one primary local text lane unless a benchmark or migration explicitly needs
more:

- `llama-cpp` is the canonical local text serving lane for agent-facing work.
- OVMS is the reviewed Intel/OpenVINO embedding lane.
- Gemma 4 E2B belongs in the Intel-aware stack as an explicit `llama.cpp`
  GGUF text overlay, not as an OVMS text-generation promotion. Use
  `compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml` with an
  Intel-aware preset when the current task needs that bounded Spark lane.
  This lane disables OpenAI literal-completions in `langchain-api` because
  the Gemma 4 chat-template path validates through chat-completions, while
  the completions shortcut returned empty text during exact-reply smoke. Native
  idle sleep owns memory release, with a 4 GiB soft reclaim reservation and no
  private hard memory ceiling.
- Ollama and LiteLLM are retained fallback/control surfaces, not the default
  path.
- Alternate llama sidecars and Intel text overlays are lab or promotion
  surfaces until separately reviewed.

When memory pressure is the problem, tune the active model lane first: context
size, KV cache type, batch size, thread count, prompt cache, and preset choice.
Do not remove storage, dictation, or TTS contracts to compensate for an
oversized model lane.

Keep retrieval model classes separate from the text lane. Embeddings can stay on
OVMS in `intel-worker`; reranking uses the explicit `reranking` profile when it
should be stack-resident, not the `llama.cpp` OpenVINO backend.
The current host-validated Qwen3 reranker is an OpenVINO CausalLM canary, not a
drop-in OVMS `/v3/rerank` artifact, so `45-rerank-api.yml` wraps the proven
scorer behind a lazy localhost API.
The wrapper unloads after the configured idle window
(`AOA_RERANK_IDLE_UNLOAD_SEC`, default `900`) so reranking can stay available
without keeping another multi-GB model resident between retrieval bursts.
Because the Python/OpenVINO allocator may retain freed pages inside the process,
idle unload exits the rerank process by default
(`AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD=true`) and relies on the container restart
policy to bring back a clean lightweight API.
Owner-triggered relief uses the separate
`AOA_RERANK_EXIT_AFTER_MEMORY_RELIEF` switch, drains new requests before the
restart, and preserves a bounded action receipt under `Logs/rerank-api` so a
retry cannot repeat or reinterpret the same action ID.

The `rag` profile is the first promoted orchestration layer for RAG and
Agentic-RAG preparation. It adds only `rag-api` on top of the existing storage,
embedding, route, rerank, and text lanes. It owns source-linked ingest,
retrieval composition, optional rerank calls, grounded-answer requests, agentic
trace shape, and DAG job manifests. It does not make n8n, Dagster, or Temporal
resident; those remain explicit workflow/durable-execution lanes until real
load proves that the local RAG control plane needs them.

## Timer Discipline

Timers are the right form for evidence, index, semantic, doctor, and monitoring
work, but their cadence must stay proportional to the value of the data:

- frequent timers need bounded work, low priority, and explicit skip behavior
- heavy timers should route through `abyss-machine resource launch`
- periodic policy reconciliation should use the light path when available
- add `RandomizedDelaySec` when a timer does not need exact wall-clock timing
- use `MemoryHigh`, `CPUWeight`, `IOWeight`, `Nice`, and idle IO scheduling for
  background work

Optimization starts by reducing redundant cadence, log noise, and resource
priority. Disabling a working service is a lifecycle decision, not a default
optimization technique.

## Resource Guard Overlays

Use tuning overlays when the selected service set is correct but the machine
needs owner-native budgets, soft reclaim reservations, retention, or sampling
posture:

| Overlay | Use With | Purpose |
|---|---|---|
| `compose/tuning/storage.intel-285h.resource-guard.yml` | `substrate` or presets containing it | keeps database-native budgets and soft reclaim reservations without private CPU or memory ceilings |
| `compose/tuning/intel-worker.thin-host.yml` | `intel-worker` or presets containing it | keeps OVMS and `langchain-api` elastic while preserving soft reclaim protection and owner-native thread tuning |
| `compose/tuning/federation.thin-host.yml` | `federation` | keeps advisory `route-api` soft-reserved without changing federation surfaces |
| `compose/tuning/observability.thin-host.yml` | `observability`, `agent-observability`, `intel-observability`, full presets | keeps dashboards, PromQL, and LogQL available with shorter retention, lower cAdvisor cadence, and elastic collector services |
| `compose/tuning/tools.thin-host.yml` | `tools`, `agent-tools`, `intel-tools`, full presets | keeps speech/browser helpers soft-reserved and owner-managed when selected |
| `compose/tuning/workflows.thin-host.yml` | `workflows` | keeps n8n owner-native concurrency and V8 budgets while workflows remain opt-in |
| `compose/tuning/rag.thin-host.yml` | `rag` | keeps `rag-api` elastic and RAG embedding batches conservative |

Do not apply a helper overlay to a preset that does not select the matching
services; use the profile-specific overlay with the profile that owns those
services.

OVMS is a trusted, reloadable model owner rather than an untrusted batch job.
On the current cgroup v2 host, its former `4g` hard ceiling filled the matching
private swap allowance while physical memory remained available. The worker
overlay therefore keeps `mem_reservation` as best-effort reclaim protection and
uses OVMS health, config reload, embedding parity, and rollback as its lifecycle
boundary instead of imposing `mem_limit`.

The same owner rule applies to the persistent thin-host services. Their
overlays intentionally render `cpus: "0"` and `mem_limit: "0"` to clear
inherited cgroup ceilings while retaining soft reservations and service-native
budgets. A static ceiling is valid only in a separate measured lab or an
explicitly disposable workload, never as the normal orchestration mechanism
for a selected owner service.

Persist host-local overlay choices through `scripts/aoa-install-systemd` instead
of editing the source unit skeleton or relying on a shell export. The live
systemd route should carry the full intended shape in one drop-in:

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation,reranking,rag --overlay compose/tuning/storage.intel-285h.resource-guard.yml,compose/tuning/intel-worker.thin-host.yml,compose/tuning/federation.thin-host.yml,compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml,compose/tuning/observability.thin-host.yml,compose/tuning/tools.thin-host.yml,compose/tuning/rag.thin-host.yml
```

Do not pass `--restart-now` while the workstation is busy unless the operator
has explicitly opened a restart window. Without a restart, the drop-in is staged
for the next controlled `podman-compose-abyss.service` restart or reload.
Use `scripts/aoa-apply-resource-guards --dry-run` to verify that the game guard
and exact rendered-vs-live CPU and memory values agree before applying the
staged guards. A removed guard expects an unlimited live value, so an old hard
ceiling remains `staged_not_applied` until the container is recreated. The
apply wrapper refuses to touch the live stack while an active game is detected
unless `--force` is passed. Its default `recreate` method reloads the user unit
with a temporary `AOA_UP_FORCE_RECREATE=1` environment so already-running
containers are recreated with the staged cgroup limits. Use `--method reload`
only for a lighter best-effort apply, or `--method restart` when a full down/up
window is acceptable.
When the workstation is occupied but the operator wants the apply to happen as
soon as the safe window opens, use
`scripts/aoa-apply-resource-guards --wait-game-guard-clear --wait-resource-plan-clear`;
it keeps the same game guard semantics, checks the current sampled
`abyss-machine resource plan` for medium generic unattended work, and applies
only after both gates clear.

## Inspection Route

Use these checks before changing a live service selection:

```bash
systemctl --user list-unit-files 'abyss-*' 'aoa-*' 'ydotoold.service'
systemctl list-unit-files 'abyss-*' 'aoa-*' 'ydotool*'
systemctl --user list-timers --all 'abyss-*' 'aoa-*'
systemctl list-timers --all 'abyss-*' 'aoa-*'
podman ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
podman stats --no-stream
```

Then validate source and deployed contracts:

```bash
scripts/aoa-status --optimization
scripts/aoa-status --optimization-audit
scripts/aoa-status --optimization-audit --require-complete
scripts/aoa-status --service-selection
scripts/aoa-status --resource-guards
scripts/aoa-apply-resource-guards --dry-run
systemd-analyze --user verify systemd/user/*.service systemd/user/*.timer systemd/user/*.path
systemd-analyze verify systemd/system/*.service systemd/system/*.timer
python scripts/validate_stack.py
python scripts/validate_stack.py --parity-check
```
