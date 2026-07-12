# KAG Runtime Seam

## Role

The KAG runtime seam turns the verified repo-self projection bundle from
`aoa-kag` into local search and graph stores. Every result remains traceable to
the owner-qualified records and source anchors carried by that bundle.

## Input

The bundle contains:

- `manifest.json`, binding canonical owner inputs, projection identities,
  embedding profile, counts, and file digests;
- JSONL streams for owners, nodes, relations, external references, and
  retrieval documents;
- stable vector point identities prepared by `aoa-kag`.

The promoted embedding profile is stored at
`config-templates/Configs/rag/repo-self-kag-embedding-profile.json`. Its model,
revision digest, dimensions, distance, and normalization are part of the
projection identity.

## Runtime Topology

`scripts/aoa-kag-runtime-projection` writes mutable state under:

```text
${AOA_STACK_ROOT}/Knowledge/kag/repo-self/
  exact/repo-self.sqlite3
  receipts/<projection-digest>/<target>.json
  current.json
```

The target adapters are:

| Target | Runtime output | Function |
|---|---|---|
| `exact` | SQLite plus FTS5 | owner, node, relation, artifact, anchor, filter, and BM25 reads |
| `vector` | versioned Qdrant collection and `aoa_kag_repo_self_current` alias | semantic and hybrid retrieval |
| `graph` | versioned Neo4j owner/node/relation subgraph and current marker | hierarchy, cross-repo, and multi-hop traversal |

Each adapter completes and verifies its new version before switching its
current pointer. One previous remote projection remains available for rollback;
older managed projections are reclaimed.

Vector builds resume an incomplete versioned collection from its confirmed
document prefix. Transient embedding failures are retried, and a batch that
exceeds live model capacity is split while preserving document order.

## Operation

Build the bundle with `aoa-kag`, then materialize selected targets:

```bash
scripts/aoa-kag-runtime-projection \
  --bundle-dir /path/to/repo-self-bundle \
  --target all
```

Verify the active projections against the same bundle:

```bash
scripts/aoa-kag-runtime-projection \
  --bundle-dir /path/to/repo-self-bundle \
  --target all \
  --check
```

Embedding, Qdrant, and Neo4j endpoints are host-local by default and can be
selected through the corresponding `AOA_KAG_*` environment variables. Neo4j
credentials come from `AOA_KAG_NEO4J_*`, `AOA_RAG_NEO4J_*`, `NEO4J_AUTH`, or
the deployed `Secrets/Configs/stack.env`.
Receipts expose endpoint-independent identities, counts, durations, and output
handles.

## Ownership

Each repository owns its canonical `/kag` records. `aoa-kag` owns their common
language, builders, federation, and retrieval bundle. `abyss-stack` owns the
mutable runtime stores, cutover, retention, and receipts described here.

The existing `aoa-kag` and `tos-source` mirrors remain the advisory-only
inspection route for `/kag/*` and the source-owned `Tree-of-Sophia` handoff:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
```
