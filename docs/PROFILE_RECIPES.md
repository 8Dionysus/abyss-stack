# PROFILE RECIPES

This document answers a practical question for each profile:

**what should I expect to become reachable after startup, and what should I check first?**

## Common pattern

For any profile:

```bash
scripts/aoa-profile-modules --profile <name> --paths
scripts/aoa-profile-endpoints --profile <name>
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
scripts/aoa-up --profile intel
scripts/aoa-wait --profile intel
scripts/aoa-smoke --profile intel
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
scripts/aoa-up --profile observability
scripts/aoa-wait --profile observability
scripts/aoa-smoke --profile observability
scripts/aoa-internal-probes --profile observability
```
