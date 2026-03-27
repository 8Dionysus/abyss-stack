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

For profiles that include local Ollama inference, `aoa-up` now performs a post-start warmup of `qwen3.5:9b` and relies on Ollama keep-alive to avoid repeated cold loads during normal short idle periods.

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
- `ollama` -> `http://127.0.0.1:11434/api/tags`

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
This profile is Ollama-first for embeddings and does not require OVMS.

### Host-facing endpoints

All `core` endpoints, plus:
- `litellm` -> `127.0.0.1:4000`
- `langchain-api` -> `http://127.0.0.1:5401/health`

### First checks

```bash
scripts/aoa-profile-endpoints --profile agentic
scripts/aoa-render-services --profile agentic
scripts/aoa-up --profile agentic
scripts/aoa-wait --profile agentic
scripts/aoa-smoke --profile agentic
```

## `intel`

### What it is for

The Intel-aware agent runtime.
This profile adds OVMS and applies the Intel overlay for the agent API, switching embeddings to OVMS.

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
```

## `federation`

### What it is for

A localhost-only federation seam that reads mirrored `aoa-agents` contracts, mirrored `aoa-routing` advisory surfaces, mirrored `aoa-memo` recall surfaces, and mirrored `aoa-evals` eval-selection surfaces from the runtime tree.
This profile is metadata-only for reads and does not change `langchain-api`, but it also enables filesystem-first memo export candidates and filesystem-first eval export candidates.

### Host-facing endpoints

- `route-api` -> `http://127.0.0.1:5402/health`

### First checks

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-profile-endpoints --profile federation
scripts/aoa-render-services --profile federation
scripts/aoa-up --profile federation
scripts/aoa-wait --profile federation
scripts/aoa-smoke --profile federation
```

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
```

### `agentic + federation`

What it gives you:
- the generic local agent path
- a localhost-only federation seam for mirrored `aoa-agents` contracts, `aoa-routing` advisory surfaces, `aoa-memo` recall surfaces, and `aoa-evals` eval-selection surfaces
- filesystem-first memo export candidates under `Logs/memo-exports/`
- filesystem-first eval export candidates under `Logs/eval-exports/`
- no change to the existing `/run` or `/embeddings` surfaces

Try:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-profile-modules --profile agentic --profile federation --paths
scripts/aoa-profile-endpoints --profile agentic --profile federation
scripts/aoa-render-services --profile agentic --profile federation
scripts/aoa-up --profile agentic --profile federation
scripts/aoa-smoke --profile agentic --profile federation
```

### `intel + federation`

What it gives you:
- the Intel-aware agent runtime with OVMS
- the same localhost-only federation seam, `aoa-routing` advisory layer, `aoa-memo` recall layer, and `aoa-evals` eval-selection layer
- the same filesystem-first memo export candidates
- filesystem-first eval export candidates under `Logs/eval-exports/`
- no change to the existing Intel overlay contract

Try:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
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
```
