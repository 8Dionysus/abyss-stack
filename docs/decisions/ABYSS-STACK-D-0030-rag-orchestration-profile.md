# RAG Orchestration Profile

- Decision ID: ABYSS-STACK-D-0030
- Status: accepted
- Date: 2026-05-16
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-16
- Surface classes: runtime profile, federation/read-model
- Stack lanes: service selection, profiles and presets
- Mechanic parents: config-projection, federation-seams
- Guard families: service selection, profile composition
- Posture: accepted RAG profile rationale

## Context

The stack already had the main RAG primitives: Qdrant, Neo4j, Postgres, Redis,
OVMS embeddings, a lazy Qwen3 reranker, route-api advisory surfaces, and the
canonical `langchain-api -> llama.cpp` text lane. What it lacked was a bounded
runtime surface that ties those primitives together into source-linked ingest,
retrieval, grounded answer, Agentic-RAG trace, and DAG job manifests.

## Options considered

1. Treat n8n as the RAG brain and build RAG mostly as workflows.
2. Add another vector database or retrieval platform.
3. Make Temporal or Dagster resident before the local RAG contract exists.
4. Add a small `rag-api` service and `rag` profile over the existing stores,
   model lanes, and advisory seams.

## Decision

Add `compose/modules/46-rag-api.yml` and `compose/profiles/rag.txt` as the
first RAG orchestration layer.

`rag-api` consumes public-safe manifests under `Configs/rag/`, reads mounted
runtime source mirrors, writes source-linked chunks into Qdrant, retrieves by
embedding through `langchain-api`, optionally reranks through `rerank-api`, and
generates grounded answers through the existing local text lane. It also exposes
Agentic-RAG graph and DAG job manifests without making a heavier workflow engine
resident by default.

## Rationale

This keeps the runtime explicit and avoids duplicating infrastructure that is
already working. Qdrant remains the vector store, Neo4j remains the graph store,
OVMS remains the embeddings lane, rerank remains lazy and bounded, and
`route-api` remains advisory.

n8n is still useful for integrations and scheduled workflow automation, but it
should not own retrieval semantics. Dagster and Temporal are useful future
routes for asset checks or durable long-running workflows, but making them
resident before the local RAG contract is proven would add memory pressure and
another orchestration layer without fixing chunking, provenance, or eval.

## Consequences

- The stack now has a concrete localhost RAG API surface to smoke, ingest, and
  evolve.
- Source-linked chunk schema, source registry, Agentic-RAG graph shape, and DAG
  jobs have public-safe runtime manifests.
- The first RAG path can be validated without starting n8n, Dagster, or
  Temporal.
- The service is intentionally v0: hybrid dense+sparse retrieval, graph
  expansion, eval scoring, and durable checkpointers remain future additions.

## Source surfaces

- `compose/modules/46-rag-api.yml`
- `compose/profiles/rag.txt`
- `compose/tuning/rag.thin-host.yml`
- `config-templates/Configs/rag/`
- `config-templates/Services/rag-api/`
- `docs/runtime/SERVICE_SELECTION.md`
- `docs/runtime/SERVICE_CATALOG.md`
- `docs/profiles/PROFILES.md`
- `docs/profiles/PROFILE_RECIPES.md`

## Follow-up route

Revisit after the first real corpus ingestion/eval pass. If ingestion grows
beyond local v0, add asset checks and lineage through a dedicated DAG profile.
If agent runs need crash-proof multi-hour durability, add a Temporal lane behind
an explicit profile rather than merging it into `rag`.
