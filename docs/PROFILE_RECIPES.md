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

Before screening a new donor, open or create its entry in
[MODEL_CARDS](MODEL_CARDS.md) and keep the donor explicit in the packet.

Model-card-first Intel text screening:

```bash
scripts/aoa-sync-configs
export AOA_OVMS_TEXT_SOURCE_MODEL=OpenVINO/Qwen3-8B-int4-ov
export AOA_OVMS_TEXT_MODEL_NAME=OpenVINO/Qwen3-8B-int4-ov
podman compose \
  -f /srv/abyss-stack/Configs/compose/tuning/intel-text.ovms-gpu-lab.yml \
  -f /srv/abyss-stack/Configs/compose/tuning/intel-text.ovms-qwen3-settings.yml \
  up -d
scripts/aoa-qwen-check --case exact-reply --url http://127.0.0.1:5404/run
scripts/aoa-qwen-bench --profile intel --url http://127.0.0.1:5404/run --backend-label "langchain-api-intel-text -> ovms-openai" --model-label "OpenVINO/Qwen3-8B-int4-ov" --runtime-variant "OVMS text-generation sidecar on GPU" --target-label "intel-text-qwen3-8b-int4-gpu-lab"
```

For the first explicit non-`llama.cpp` Intel text lane, use the standalone OVMS sidecar lab packet instead of rewriting the canonical profile:

```bash
scripts/aoa-sync-configs
export AOA_OVMS_TEXT_SOURCE_MODEL=OpenVINO/Qwen3-8B-int4-ov
export AOA_OVMS_TEXT_MODEL_NAME=OpenVINO/Qwen3-8B-int4-ov
podman compose \
  -f /srv/abyss-stack/Configs/compose/tuning/intel-text.ovms-gpu-lab.yml \
  -f /srv/abyss-stack/Configs/compose/tuning/intel-text.ovms-qwen3-settings.yml \
  up -d
scripts/aoa-qwen-check --case exact-reply --url http://127.0.0.1:5404/run
scripts/aoa-qwen-bench --profile intel --url http://127.0.0.1:5404/run --backend-label "langchain-api-intel-text -> ovms-openai" --model-label "OpenVINO/Qwen3-8B-int4-ov" --runtime-variant "OVMS text-generation sidecar on GPU" --target-label "intel-text-qwen3-8b-int4-gpu-lab"
```

Use [LLAMACPP_PILOT](LLAMACPP_PILOT.md) for the full operator contract.

## `core`

### What it is for

The smallest useful local substrate.
Good for validating storage, orchestration, and local model-serving basics.

### Host-facing endpoints

- `postgres` -> `127.0.0.1:5432`
- `redis` -> `127.0.0.1:6379`
- `qdrant` -> `http://127.0.0.1:6333/`
- `neo4j` -> `http://127.0.0.1:7474/`
- `n8n` -> `http://127.0.0.1:5678/`
- `llama-cpp` -> `http://127.0.0.1:11435/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile core
scripts/aoa-render-services --profile core
scripts/aoa-up --profile core
scripts/aoa-wait --profile core
scripts/aoa-smoke --profile core
```

## `agentic`

### What it is for

The generic local agent runtime.
This profile uses `langchain-api -> llama.cpp` as the canonical chat path and does not require OVMS.

### Host-facing endpoints

All `core` endpoints, plus:
- `langchain-api` -> `http://127.0.0.1:5403/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile agentic
scripts/aoa-render-services --profile agentic
scripts/aoa-up --profile agentic
scripts/aoa-wait --profile agentic
scripts/aoa-smoke --profile agentic
scripts/aoa-qwen-check --case exact-reply
scripts/aoa-qwen-bench --profile agentic
```

## `intel`

### What it is for

The Intel-aware agent runtime.
This profile adds OVMS and applies the Intel overlay for the canonical agent API.
In the current reviewed posture, embeddings move to OVMS while the canonical chat path stays on `llama.cpp`.
Broader Intel-serving lanes remain additive and separately reviewed rather than silently promoted through this profile.
If you are screening an explicit Intel-served text lane, point `langchain-api` at it through `LC_BASE_URL`, `LC_API_KEY`, and `LC_MODEL` in the secret `langchain-api.env` file rather than rewriting the profile itself.

### Host-facing endpoints

All `agentic` endpoints, plus:
- `ovms rest` -> `http://127.0.0.1:8200/v2/health/live`
- `ovms grpc` -> `127.0.0.1:9200`

### First checks

```bash
scripts/aoa-doctor
scripts/aoa-profile-endpoints --profile intel
scripts/aoa-render-services --profile intel
scripts/aoa-up --profile intel
scripts/aoa-wait --profile intel
scripts/aoa-smoke --profile intel
scripts/aoa-qwen-check --case exact-reply
scripts/aoa-qwen-bench --profile intel
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

A preview-first route helper for Tree of Sophia graph curation.
This slice uses the storage substrate so `neo4j` is available, but it keeps the
helper itself read-first and localhost-only.
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

### `agentic + tools`

What it gives you:
- the generic local agent path
- speech endpoints on the host
- browser-tools surfaces kept internal-only

Try:

```bash
scripts/aoa-profile-modules --profile agentic --profile tools --paths
scripts/aoa-profile-endpoints --profile agentic --profile tools
scripts/aoa-render-services --profile agentic --profile tools
scripts/aoa-up --profile agentic --profile tools
scripts/aoa-smoke --with-internal --profile agentic --profile tools
```

Preset form:

```bash
aoa-preset-profiles --preset agent-tools --paths
aoa-up --preset agent-tools
aoa-smoke --with-internal --preset agent-tools
aoa-qwen-bench --preset agent-tools
```

### `agentic + observability`

What it gives you:
- the generic local agent path
- dashboards and metrics visibility
- internal-only `cadvisor`

Try:

```bash
scripts/aoa-profile-modules --profile agentic --profile observability --paths
scripts/aoa-profile-endpoints --profile agentic --profile observability
scripts/aoa-render-services --profile agentic --profile observability
scripts/aoa-up --profile agentic --profile observability
scripts/aoa-smoke --with-internal --profile agentic --profile observability
```

Preset form:

```bash
aoa-preset-profiles --preset agent-observability --paths
aoa-up --preset agent-observability
aoa-smoke --with-internal --preset agent-observability
aoa-qwen-bench --preset agent-observability
```

### `agentic + federation`

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
scripts/aoa-profile-modules --profile agentic --profile federation --paths
scripts/aoa-profile-endpoints --profile agentic --profile federation
scripts/aoa-render-services --profile agentic --profile federation
scripts/aoa-up --profile agentic --profile federation
scripts/aoa-smoke --profile agentic --profile federation
```

### `intel + federation`

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
scripts/aoa-profile-modules --profile intel --profile federation --paths
scripts/aoa-profile-endpoints --profile intel --profile federation
scripts/aoa-render-services --profile intel --profile federation
scripts/aoa-up --profile intel --profile federation
scripts/aoa-smoke --profile intel --profile federation
```

### `intel + tools + observability`

What it gives you:
- Intel-aware agent runtime with OVMS
- speech helpers
- observability surfaces
- all internal-only surfaces checked in one pass

Try:

```bash
scripts/aoa-profile-modules --profile intel,tools,observability --paths
scripts/aoa-profile-endpoints --profile intel,tools,observability
scripts/aoa-render-services --profile intel,tools,observability
scripts/aoa-up --profile intel,tools,observability
scripts/aoa-smoke --with-internal --profile intel,tools,observability
```

Preset form:

```bash
aoa-preset-profiles --preset intel-full --paths
aoa-up --preset intel-full
aoa-smoke --with-internal --preset intel-full
aoa-qwen-bench --preset intel-full
```
