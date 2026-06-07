# ARCHITECTURE

## One-line model

`abyss-stack` is the operational body of AoA and ToS.

## Layer model

The default working runtime selection is `substrate`: storage only. Workflow
automation, local workers, retained fallback gateways, Intel lanes, federation
seams, tools, and observability are explicit profile or preset layers over that
base.

### 1. Storage layer

Persistent state and retrieval substrate:
- Postgres
- Redis
- Qdrant
- Neo4j

### 2. Workflow automation layer

Optional workflow coordination and pipeline surfaces:
- n8n under the explicit `workflows` profile
- LangGraph remains a bounded local-worker execution surface rather than part
  of the default substrate profile

### 3. Inference layer

Local and accelerator-aware model serving:
- Ollama remains a retained fallback/control serving lane, not the default
  AbyssOS substrate
- llama.cpp as the canonical local GGUF-serving path for bounded local-worker flows
- OVMS as the current reviewed Intel/OpenVINO-oriented serving seam, currently exercised for embeddings in the promoted Intel presets
- broader Intel serving lanes across OVMS, OpenVINO, and future OpenVINO GenAI may host other model classes through separate reviewed profile, machine-fit, or rollout changes
- a future OpenVINO GenAI migration or promotion of a non-llama.cpp Intel-served text lane is a separate stack change, not part of the current promoted path

### 4. Gateway and agent API layer

Model routing and agent-facing runtime APIs:
- LiteLLM remains a retained fallback gateway lane paired with Ollama in
  `fallback-gateway`
- LangChain API as the single canonical local-worker runtime surface on `5403`

This layer may also host the runtime return wrapper that rebuilds context from a last valid anchor rather than continuing under drift.

### 5. Speech and tool layer

Optional runtime helpers:
- TTS services
- browser and docs helper services

### 6. Monitoring layer

Optional observability:
- Prometheus
- Grafana
- Alertmanager
- cAdvisor
- Loki
- Alloy

## Module map

The stack is decomposed into explicit compose modules under `compose/modules/`.

The intended rule is simple:
- one concern per module
- no swollen all-in-one compose file
- optional capability stays optional

## Trust boundaries

- host-facing ports bind to localhost
- internal-only services should stay internal-only
- env examples may live in repo
- real secrets do not live in repo

## Platform stance

The stack is Fedora-first as a deployed runtime.
Windows usability is achieved by separating:
- source checkout paths
- deployed Linux runtime paths
- optional host-side vault paths

## Ecosystem boundaries

Sibling AoA repositories own authored meaning.
This repository only owns the runtime substrate that supports those layers.
