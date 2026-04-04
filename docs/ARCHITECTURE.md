# ARCHITECTURE

## One-line model

`abyss-stack` is the operational body of AoA and ToS.

## Layer model

### 1. Storage layer

Persistent state and retrieval substrate:
- Postgres
- Redis
- Qdrant
- Neo4j

### 2. Orchestration layer

Workflow coordination and pipeline surfaces:
- n8n
- LangGraph for bounded local-worker execution, pause/resume, and milestone-gated recovery flows

### 3. Inference layer

Local and accelerator-aware model serving:
- llama.cpp as the canonical local GGUF-serving path for bounded local-worker flows
- OVMS as the current Intel/OpenVINO-oriented serving path for embeddings
- a future OpenVINO GenAI migration as a separate stack change, not part of the current promoted path

### 4. Gateway and agent API layer

Model routing and agent-facing runtime APIs:
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
