# PROFILE RECIPES

This document answers a practical question for each profile:

**what should I expect to become reachable after startup, and what should I check first?**

## Common pattern

For any profile:

```bash
scripts/aoa-profile-modules --profile <name> --paths
scripts/aoa-profile-endpoints --profile <name>
scripts/aoa-render-services --profile <name>
scripts/aoa-up --profile <name>
scripts/aoa-wait --profile <name>
scripts/aoa-smoke --profile <name>
```

If the profile includes internal-only services, follow with:

```bash
scripts/aoa-internal-probes --profile <name>
```

Or combine host-facing and internal-only checks in one pass:

```bash
scripts/aoa-smoke --with-internal --profile <name>
```

For profiles that include canonical `llama.cpp` inference, `aoa-up` now performs a bounded readiness wait on the `llama.cpp` health surface before handing control back to the operator.

## Optional benchmark lane

If you want a bounded alternate `llama.cpp` benchmark or promotion lane beyond the canonical runtime path, use:

```bash
scripts/aoa-llamacpp-pilot run --preset intel-full
```

That lane is separate from the canonical profile-driven runtime and exists only for explicit benchmark or promotion work.
Use the same explicit lane for additive Intel 285H host-profile work such as Gemma 4 screening, Vulkan-first validation, or KV-cache candidate checks.
Keep those runs as benchmark or promotion artifacts until machine-fit and reviewed runtime docs say otherwise.

Common Intel 285H candidate examples:

```bash
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.cpu-safe.yml
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.cpu-balanced.yml --overlay compose/tuning/llamacpp.intel-285h.server-cache.yml
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.vulkan-lab.yml
```

`vulkan-lab` is a dedicated image-seam packet, not just a device flag. It
swaps `llama-cpp` to `ghcr.io/ggml-org/llama.cpp:server-vulkan` for that run.

When one of those challenger packets looks strong enough to replace the current
live winner, move to
[RUNTIME_WINNER_PROMOTION_LOOP](../../mechanics/inference-pilots/parts/promotion-loop/docs/RUNTIME_WINNER_PROMOTION_LOOP.md) rather than
promoting directly from the pilot output.

Before screening a new donor, open or create its entry in
[MODEL_CARDS](../../mechanics/machine-fit/parts/inference-tuning/docs/MODEL_CARDS.md)
and keep the donor explicit in the packet. For the first explicit
non-`llama.cpp` Intel text lane, use the standalone OVMS sidecar lab packet
instead of rewriting the canonical profile:

```bash
scripts/aoa-sync-configs
export AOA_OVMS_TEXT_SOURCE_MODEL=OpenVINO/Qwen3-8B-int4-ov
export AOA_OVMS_TEXT_MODEL_NAME=OpenVINO/Qwen3-8B-int4-ov
podman compose \
  -f /srv/AbyssOS/abyss-stack/Configs/compose/tuning/intel-text.ovms-gpu-lab.yml \
  -f /srv/AbyssOS/abyss-stack/Configs/compose/tuning/intel-text.ovms-qwen3-settings.yml \
  up -d
scripts/aoa-qwen-check --case exact-reply --url http://127.0.0.1:5404/run
scripts/aoa-qwen-bench --profile intel-worker --url http://127.0.0.1:5404/run --backend-label "langchain-api-intel-text -> ovms-openai" --model-label "OpenVINO/Qwen3-8B-int4-ov" --runtime-variant "OVMS text-generation sidecar on GPU" --target-label "intel-text-qwen3-8b-int4-gpu-lab"
```

Use [LLAMACPP_PILOT](../../mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md) for the full operator contract.

## `substrate`

### What it is for

The conservative working AbyssOS runtime base.
Good for validating storage, retrieval, config projection, and root lifecycle
without silently selecting workflow automation, a model worker, or a federation
seam.

### Host-facing endpoints

- `postgres` -> `127.0.0.1:5432`
- `redis` -> `127.0.0.1:6379`
- `qdrant` -> `http://127.0.0.1:6333/`
- `neo4j` -> `http://127.0.0.1:7474/`

### First checks

```bash
scripts/aoa-profile-endpoints --profile substrate
scripts/aoa-render-services --profile substrate
scripts/aoa-up --profile substrate
scripts/aoa-wait --profile substrate
scripts/aoa-smoke --profile substrate
```

## `workflows`

### What it is for

Optional n8n workflow automation and task-runner support.
Use it only when workflow automation is intentionally part of the run being
checked. It includes the storage dependency, and it can be composed over
`substrate` without duplicating modules.

### Host-facing endpoints

- `postgres` -> `127.0.0.1:5432`
- `redis` -> `127.0.0.1:6379`
- `qdrant` -> `http://127.0.0.1:6333/`
- `neo4j` -> `http://127.0.0.1:7474/`
- `n8n` -> `http://127.0.0.1:5678/`

### First checks

```bash
scripts/aoa-profile-endpoints --profile workflows
scripts/aoa-render-services --profile workflows
scripts/aoa-up --profile workflows
scripts/aoa-wait --profile workflows
scripts/aoa-smoke --profile workflows
```

## `local-worker`

### What it is for

The canonical local text worker layer.
Use it with `substrate` when the runtime should expose the promoted
`langchain-api -> llama.cpp` path without moving to a broader preset.

### Host-facing endpoints

- `llama-cpp` -> `http://127.0.0.1:11435/health`
- `langchain-api` -> `http://127.0.0.1:5403/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile substrate --profile local-worker
scripts/aoa-render-services --profile substrate --profile local-worker
scripts/aoa-up --profile substrate --profile local-worker
scripts/aoa-wait --profile substrate --profile local-worker
scripts/aoa-smoke --profile substrate --profile local-worker
scripts/aoa-qwen-check --case exact-reply
```

## `intel-worker`

### What it is for

The canonical local text worker with the reviewed Intel/OVMS embeddings seam.
Use it with `substrate` when the runtime should keep chat on
`langchain-api -> llama.cpp` while moving embeddings to OVMS.

### Host-facing endpoints

- `llama-cpp` -> `http://127.0.0.1:11435/health`
- `ovms rest` -> `http://127.0.0.1:8200/v2/health/live`
- `ovms grpc` -> `127.0.0.1:9200`
- `langchain-api` -> `http://127.0.0.1:5403/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile substrate --profile intel-worker
scripts/aoa-render-services --profile substrate --profile intel-worker
scripts/aoa-up --profile substrate --profile intel-worker
scripts/aoa-wait --profile substrate --profile intel-worker
scripts/aoa-smoke --profile substrate --profile intel-worker
scripts/aoa-qwen-check --case exact-reply
```

## `core`

### What it is for

Compatibility bundle for substrate plus local model-serving basics.
Good for older operator habits and quick storage/`llama.cpp` checks. For the
source-owned OS base, prefer `substrate`; for the full agent API path, prefer
`substrate + local-worker` or `substrate + intel-worker`. Add `workflows`
explicitly when n8n is part of the check.

### Host-facing endpoints

- `postgres` -> `127.0.0.1:5432`
- `redis` -> `127.0.0.1:6379`
- `qdrant` -> `http://127.0.0.1:6333/`
- `neo4j` -> `http://127.0.0.1:7474/`
- `llama-cpp` -> `http://127.0.0.1:11435/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile core
scripts/aoa-render-services --profile core
scripts/aoa-up --profile core
scripts/aoa-wait --profile core
scripts/aoa-smoke --profile core
```

## `fallback-gateway`

### What it is for

Retained Ollama plus LiteLLM control path.
Use it when checking the rollback/fallback gateway lane intentionally. It is not
the default substrate and not the promoted local-worker path.

### Host-facing endpoints

- `ollama` -> `http://127.0.0.1:11434/api/tags`
- `litellm` -> `127.0.0.1:4000`

### First checks

```bash
scripts/aoa-profile-endpoints --profile fallback-gateway
scripts/aoa-render-services --profile fallback-gateway
scripts/aoa-up --profile fallback-gateway
scripts/aoa-wait --profile fallback-gateway
scripts/aoa-smoke --profile fallback-gateway
```

## `agentic`

### Compatibility bridge

`agentic` is the retained generic local-agent selector for older operator
habits and scripts. It is not the current recipe owner. Use
`substrate + local-worker` for normal launch, smoke, and bench flows.

Bridge check:

```bash
scripts/aoa-profile-modules --profile agentic --paths
scripts/aoa-render-services --profile agentic
```

## `intel`

### Compatibility bridge

`intel` is the retained Intel-aware selector for older operator habits and
scripts. It is not the current recipe owner. Use `substrate + intel-worker`
for normal launch, smoke, bench, and OVMS-embedding flows.

Bridge check:

```bash
scripts/aoa-profile-modules --profile intel --paths
scripts/aoa-render-services --profile intel
```

## `federation`

### What it is for

A localhost-only federation seam that reads mirrored `aoa-agents` contracts, mirrored `aoa-routing` advisory surfaces, mirrored `aoa-memo` recall surfaces, mirrored `aoa-evals` eval-selection surfaces, mirrored `aoa-playbooks` activation/composition advisory surfaces, mirrored `aoa-kag` retrieval/regrounding surfaces, and a source-owned `tos-source` handoff companion from the runtime tree.
This profile is metadata-only for reads and does not change `langchain-api`, but it also enables filesystem-first memo export candidates and filesystem-first eval export candidates.

### Host-facing endpoints

- `route-api` -> `http://127.0.0.1:5402/health`

### First checks

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
scripts/aoa-profile-endpoints --profile federation
scripts/aoa-render-services --profile federation
scripts/aoa-up --profile federation
scripts/aoa-wait --profile federation
scripts/aoa-smoke --profile federation
```

## `curation`

### What it is for

A route-first helper for Tree of Sophia graph curation.
This slice uses the storage substrate so `neo4j` is available, but it keeps the
helper itself projection-only, read-first, and localhost-only.
Machine-fit overlays that do not touch the selected services are skipped
automatically in this profile, so it does not silently pull in `llama-cpp`.

### Host-facing endpoints

- `postgres` -> `127.0.0.1:5432`
- `redis` -> `127.0.0.1:6379`
- `qdrant` -> `http://127.0.0.1:6333/`
- `neo4j` -> `http://127.0.0.1:7474/`
- `tos-graph` -> `http://127.0.0.1:5410/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile curation
scripts/aoa-render-services --profile curation
scripts/aoa-up --profile curation
scripts/aoa-wait --profile curation
scripts/aoa-smoke --profile curation
```

Before launch, ensure `AOA_TOS_ROOT` points at the real `Tree-of-Sophia`
checkout and `Secrets/Configs/tos-graph.env` exists in the deployed runtime.
If `TOS_GRAPH_NEO4J_PASSWORD` is not set there, `tos-graph` falls back to the
mounted `${AOA_STACK_ROOT}/Configs/stack.env` and derives the password from
`NEO4J_AUTH`.

## `tools`

### What it is for

Optional helper surfaces for speech and browser-like tooling.

### Host-facing endpoints

- `qwen-tts` -> `http://127.0.0.1:5101/health`
- `tts-router` -> `http://127.0.0.1:5201/health`

### Internal-only notes

- `docs-api` is internal-only
- `aoa-browser` is internal-only

### First checks

```bash
scripts/aoa-profile-endpoints --profile tools
scripts/aoa-render-services --profile tools
scripts/aoa-up --profile tools
scripts/aoa-wait --profile tools
scripts/aoa-smoke --profile tools
scripts/aoa-internal-probes --profile tools
```

## `observability`

### What it is for

Optional visibility into the body rather than the body itself.

### Host-facing endpoints

- `prometheus` -> `http://127.0.0.1:9090/-/ready`
- `alertmanager` -> `http://127.0.0.1:9093/-/ready`
- `grafana` -> `http://127.0.0.1:3000/api/health`

### Internal-only notes

- `cadvisor` is internal-only

### First checks

```bash
scripts/aoa-profile-endpoints --profile observability
scripts/aoa-render-services --profile observability
scripts/aoa-up --profile observability
scripts/aoa-wait --profile observability
scripts/aoa-smoke --profile observability
scripts/aoa-internal-probes --profile observability
```

## Common combined recipes

### `substrate + local-worker`

What it gives you:
- the working AbyssOS substrate
- the canonical local text worker path
- no federation seam, helper tools, or observability bundle unless added later

Try:

```bash
scripts/aoa-profile-modules --profile substrate --profile local-worker --paths
scripts/aoa-profile-endpoints --profile substrate --profile local-worker
scripts/aoa-render-services --profile substrate --profile local-worker
scripts/aoa-up --profile substrate --profile local-worker
scripts/aoa-smoke --profile substrate --profile local-worker
```

### `substrate + fallback-gateway`

What it gives you:
- the working AbyssOS substrate
- retained Ollama plus LiteLLM fallback/control lane
- no promoted `langchain-api` worker unless you add `local-worker` or `intel-worker`

Try:

```bash
scripts/aoa-profile-modules --profile substrate --profile fallback-gateway --paths
scripts/aoa-profile-endpoints --profile substrate --profile fallback-gateway
scripts/aoa-render-services --profile substrate --profile fallback-gateway
scripts/aoa-up --profile substrate --profile fallback-gateway
scripts/aoa-smoke --profile substrate --profile fallback-gateway
```

### `substrate + local-worker + tools`

What it gives you:
- the generic local agent path
- speech endpoints on the host
- browser-tools surfaces kept internal-only

Try:

```bash
scripts/aoa-profile-modules --profile substrate --profile local-worker --profile tools --paths
scripts/aoa-profile-endpoints --profile substrate --profile local-worker --profile tools
scripts/aoa-render-services --profile substrate --profile local-worker --profile tools
scripts/aoa-up --profile substrate --profile local-worker --profile tools
scripts/aoa-smoke --with-internal --profile substrate --profile local-worker --profile tools
```

Preset form:

```bash
aoa-preset-profiles --preset agent-tools --paths
aoa-up --preset agent-tools
aoa-smoke --with-internal --preset agent-tools
aoa-qwen-bench --preset agent-tools
```

### `substrate + local-worker + observability`

What it gives you:
- the generic local agent path
- dashboards and metrics visibility
- internal-only `cadvisor`

Try:

```bash
scripts/aoa-profile-modules --profile substrate --profile local-worker --profile observability --paths
scripts/aoa-profile-endpoints --profile substrate --profile local-worker --profile observability
scripts/aoa-render-services --profile substrate --profile local-worker --profile observability
scripts/aoa-up --profile substrate --profile local-worker --profile observability
scripts/aoa-smoke --with-internal --profile substrate --profile local-worker --profile observability
```

Preset form:

```bash
aoa-preset-profiles --preset agent-observability --paths
aoa-up --preset agent-observability
aoa-smoke --with-internal --preset agent-observability
aoa-qwen-bench --preset agent-observability
```

### `substrate + local-worker + federation`

What it gives you:
- the generic local agent path
- a localhost-only federation seam for mirrored `aoa-agents` contracts, `aoa-routing` advisory surfaces, `aoa-memo` recall surfaces, `aoa-evals` eval-selection surfaces, `aoa-playbooks` activation/composition advisory surfaces, `aoa-kag` retrieval/regrounding surfaces, and the `tos-source` handoff companion
- filesystem-first memo export candidates under `Logs/memo-exports/`
- filesystem-first eval export candidates under `Logs/eval-exports/`
- no change to the existing `/run` or `/embeddings` surfaces

Try:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
scripts/aoa-profile-modules --profile substrate --profile local-worker --profile federation --paths
scripts/aoa-profile-endpoints --profile substrate --profile local-worker --profile federation
scripts/aoa-render-services --profile substrate --profile local-worker --profile federation
scripts/aoa-up --profile substrate --profile local-worker --profile federation
scripts/aoa-smoke --profile substrate --profile local-worker --profile federation
scripts/aoa-federated-check
```

Preset form:

```bash
aoa-preset-profiles --preset agent-federation --paths
aoa-up --preset agent-federation
aoa-smoke --preset agent-federation
aoa-federated-check
```

If you want the live federated advisory consumer path, set
`AOA_FEDERATED_RUN_ENABLED=true` in the runtime-secret
`Secrets/Configs/langchain-api.env` file before startup.
When that gate is intentionally on, prove the live advisory boundary explicitly:

```bash
scripts/aoa-federated-check --require-enabled
scripts/aoa-federated-check --require-enabled --playbook-id AOA-P-0008
scripts/aoa-federated-check --require-enabled --inspect-id AOA-K-0011
scripts/aoa-federated-check --require-enabled --memo-id AOA-M-0001
```

### `substrate + intel-worker + federation`

What it gives you:
- the Intel-aware agent runtime with OVMS
- the same localhost-only federation seam, `aoa-routing` advisory layer, `aoa-memo` recall layer, `aoa-evals` eval-selection layer, `aoa-playbooks` advisory layer, and `aoa-kag`/`tos-source` handoff layer
- the same filesystem-first memo export candidates
- filesystem-first eval export candidates under `Logs/eval-exports/`
- no change to the existing Intel overlay contract

Try:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
scripts/aoa-profile-modules --profile substrate --profile intel-worker --profile federation --paths
scripts/aoa-profile-endpoints --profile substrate --profile intel-worker --profile federation
scripts/aoa-render-services --profile substrate --profile intel-worker --profile federation
scripts/aoa-up --profile substrate --profile intel-worker --profile federation
scripts/aoa-smoke --profile substrate --profile intel-worker --profile federation
scripts/aoa-federated-check
```

Preset form:

```bash
aoa-preset-profiles --preset intel-federation --paths
aoa-up --preset intel-federation
aoa-smoke --preset intel-federation
aoa-federated-check
```

If you want the live federated advisory consumer path, set
`AOA_FEDERATED_RUN_ENABLED=true` in the runtime-secret
`Secrets/Configs/langchain-api.env` file before startup.
When that gate is intentionally on, prove the live advisory boundary explicitly:

```bash
scripts/aoa-federated-check --require-enabled
scripts/aoa-federated-check --require-enabled --playbook-id AOA-P-0008
scripts/aoa-federated-check --require-enabled --inspect-id AOA-K-0011
scripts/aoa-federated-check --require-enabled --memo-id AOA-M-0001
```

### `substrate + intel-worker + tools + observability`

What it gives you:
- Intel-aware agent runtime with OVMS
- speech helpers
- observability surfaces
- all internal-only surfaces checked in one pass

Try:

```bash
scripts/aoa-profile-modules --profile substrate,intel-worker,tools,observability --paths
scripts/aoa-profile-endpoints --profile substrate,intel-worker,tools,observability
scripts/aoa-render-services --profile substrate,intel-worker,tools,observability
scripts/aoa-up --profile substrate,intel-worker,tools,observability
scripts/aoa-smoke --with-internal --profile substrate,intel-worker,tools,observability
```

Preset form:

```bash
aoa-preset-profiles --preset intel-full --paths
aoa-up --preset intel-full
aoa-smoke --with-internal --preset intel-full
aoa-qwen-bench --preset intel-full
```
