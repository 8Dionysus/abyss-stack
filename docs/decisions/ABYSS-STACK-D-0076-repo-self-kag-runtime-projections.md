# Repo-Self KAG Runtime Projections

- Decision ID: ABYSS-STACK-D-0076
- Status: accepted
- Date: 2026-07-11
- Owner surface: `mechanics/federation-seams/parts/kag-seam/`

## Index Metadata

- Original date: 2026-07-11
- Surface classes: KAG runtime projection, exact search, vector store, graph store
- Stack lanes: federation seam, runtime knowledge, operator command
- Mechanic parents: federation-seams
- Guard families: bundle integrity, atomic cutover, owner-qualified provenance, runtime receipts
- Posture: accepted repo-self materialization rationale

## Context

OS Abyss repositories now own canonical repo-self KAG index families, and
`aoa-kag` can federate them into one source-verified retrieval projection. The
runtime needs exact, lexical, semantic, and graph access while preserving a
single identity chain back to those canonical owner records.

## Options considered

1. Materialize only a local SQLite search database.
2. Let each runtime backend independently read and interpret every repository's
   canonical `/kag` family.
3. Let `aoa-kag` emit one manifest-bound projection bundle and let
   `abyss-stack` materialize backend-specific read models from that bundle.

## Decision

Choose option 3.

`aoa-kag` emits a deterministic bundle containing owner, node, relation,
external-reference, and retrieval-document streams plus their projection and
embedding identities. `abyss-stack` verifies the complete bundle, builds
SQLite/FTS, Qdrant, and Neo4j projections, switches each current pointer after
count and identity checks, retains one prior remote projection, and records the
active state under `Knowledge/kag/repo-self/current.json`.

## Rationale

One verified input keeps all runtime stores aligned to the same canonical
snapshot. JSONL streams allow bounded-memory ingestion, stable vector point IDs
remove downstream identity inference, and versioned cutover makes rebuild and
rollback explicit. Repository truth, common KAG language, and mutable runtime
state each remain with their natural owner.

## Consequences

- Exact/filter and BM25 reads use one atomic SQLite artifact.
- Semantic retrieval uses a versioned Qdrant collection and stable alias.
- Hierarchy and multi-hop traversal use a versioned Neo4j subgraph and current
  projection marker.
- The embedding model revision participates in projection identity.
- Runtime generation cost, storage, latency, counts, and active identities are
  observable through target receipts.
- Query-serving APIs and MCP access can consume these read models through a
  later interface decision.

## Source surfaces

- `mechanics/federation-seams/parts/kag-seam/README.md`
- `mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md`
- `mechanics/federation-seams/parts/kag-seam/aoa_kag_runtime_projection.py`
- `mechanics/federation-seams/parts/kag-seam/kag_runtime/`
- `mechanics/federation-seams/parts/kag-seam/tests/test_kag_runtime_projection.py`
- `scripts/aoa-kag-runtime-projection`
- `config-templates/Configs/rag/repo-self-kag-embedding-profile.json`
- `aoa-kag:schemas/repo-local-kag-retrieval-bundle.schema.json`

## Follow-up route

Use retrieval evals and runtime receipts to tune batching, retention, and query
adapters before exposing the projections through the next KAG access plane.
