# KAG Runtime Seam

## Role

The KAG runtime seam turns machine-admitted content-addressed owner families
and the verified repo-self projection bundle from `aoa-kag` into local search
and graph stores. Every result remains traceable to the owner-qualified
records, source-index and family digests, and source anchors carried by the
bundle. When a tiered owner state is admitted, the runtime joins its exact
source ref, corpus identity, and distribution identity without treating those
delivery coordinates as source-bundle authority.

## Input

The tiered distribution input consists of:

- an immutable owner-family release bound to one exact `commit:<hex>` source
  ref;
- separate corpus and distribution manifests;
- direct content-addressed shard objects or deterministic bounded transport
  packs with exact ranges;
- a portable offline-complete bundle manifest;
- an `abyss-machine` trust-gate packet whose admitted subject-store root is the
  family root consumed by this seam;
- an optional signed OS composition containing exactly 24 verified owner
  release, corpus, and distribution digests.

The projection bundle contains:

- `manifest.json`, binding canonical owner inputs through repository identity,
  source-index digest, and the complete family-digest set, plus projection
  identities, embedding profile, counts, and file digests;
- JSONL streams for owners, nodes, relations, external references, and
  retrieval documents;
- stable vector point identities prepared by `aoa-kag`.

The verifier requires each canonical input to agree with its corresponding
owner record. It accepts the current semantic source ABI and a paired legacy
extension containing both corpus and distribution identities. Missing
semantic digests, incomplete family identity, unpaired tiered identity, or
owner-record disagreement fails closed.

The promoted embedding profile is stored at
`config-templates/Configs/rag/repo-self-kag-embedding-profile.json`. Its model,
revision digest, dimensions, distance, and normalization are part of the
projection identity.

## Runtime Topology

`scripts/aoa-kag-runtime-projection` writes mutable state under:

```text
${AOA_STACK_ROOT}/Knowledge/kag/repo-self/
  cas/objects/sha256/<prefix>/<digest>
  distribution/
    owners/<owner>/
      candidate.json
      current.json
      last-good.json
      receipts/
    composition/
      current.json
      last-good.json
    current.json
  exact/
    repo-self.sqlite3
    repo-self.last-good.sqlite3
  vector/
    owner-slices.json
    owner-slices.last-good.json
  graph/
    owner-slices.json
    owner-slices.last-good.json
  receipts/<projection-digest>/<target>.json
  current.json
```

`scripts/aoa-kag-runtime-family` owns the CAS and `distribution/` subtree. It
accepts only a supported public KAG access policy, an admitted lifecycle, an
exact source ref, verified release signatures, matching inner manifests, and a
matching machine-admitted subject-store root. It verifies bytes again before
placing them in the local CAS.

Selective owner/kind/hash-range hydration is allowed, but a partial selection
stays in `candidate.json`. Only a complete release can become
`owners/<owner>/current.json`. A composition can become current only when all
24 owner current states are complete, their exact identities match the signed
composition, and their CAS objects remain present and byte-valid.

Changing only distribution coordinates does not invalidate semantic
projections. A changed owner corpus emits owner-local projection impact with a
bounded cross-owner relation recomputation obligation. Projection refresh is a
separate visible operation; the materializer does not mutate SQLite, Qdrant,
or Neo4j as a hidden hydration side effect.

The promoted target adapters are owner-scoped:

| Target | Runtime output | Function |
|---|---|---|
| `exact` | SQLite plus FTS5 and one last-good database | owner-local transactional row/FTS refresh plus artifact, anchor, filter, and BM25 reads |
| `vector` | content-addressed Qdrant collection per owner plus current/last-good state maps | bounded owner fan-out for semantic and hybrid retrieval |
| `graph` | immutable Neo4j owner-node slices and directional owner-pair relation/reference slices plus current/last-good state maps | hierarchy, cross-repo, and multi-hop traversal constrained to active slice digests |

Each adapter completes and verifies its new version before switching its
current pointer. The exact adapter copies the last-good database, replaces only
rows and FTS entries belonging to affected owners, and refreshes relations or
external references touching those owners. Unaffected owner rows remain
byte-identical. The vector adapter embeds only affected owner documents, reuses
unchanged owner collections, embeds the query once, fans it out across the
bounded selected owner collections, and merges the global top-k. The graph
adapter writes only affected owner slices and directional owner-pair slices
touching them; traversal admits only the owner, relation, and reference slice
digests named by current state.

During the one-time migration from the legacy global vector collection to owner
collections, the bootstrap may reuse a point only when its stable point identity,
text digest, and embedding-profile identity still match. Missing or changed points
are embedded normally; the legacy alias remains intact until the owner-slice
bootstrap and checks complete.

Exact, vector, and graph each retain one last-good state. Coordinated rollback
first verifies that all three last-good targets name the same projection,
bundle, and federation identities. It refuses mixed generations, then switches
all three targets and writes one rollback receipt.

SQLite FTS indexes owner, node class, kind, path, label, and text so scoped BM25
queries stay inside their selected corpus. Qdrant indexes the matching owner,
node-class, kind, and access fields used by filtered semantic retrieval.

Vector builds resume an incomplete versioned collection from its confirmed
document prefix. A new projection reuses vectors from the current collection
when point identity, text digest, and embedding profile still match, then
embeds only changed documents. Transient embedding failures are retried, and a
batch that exceeds live model capacity is split while preserving document
order.
Graph retention resumes independently after cutover and removes older
projection nodes in bounded transactions.

## Query Application Port

`kag_runtime.application.KagApplication` is the stable read boundary above the
stores. It provides capability discovery, retrieval, addressed reads, bounded
relation traversal, and trace explanation without exposing backend-specific
operations to consumers.

The application selects exact, lexical, semantic, hybrid, graph, or composed
routes from current projection state. Each response records the requested and
used strategy, adapter timings, corpus/distribution/release identity when an
owner state exists, projection identity, degradation, provenance, source
anchors, and owner-return resources. Canonical repo-local queries remain
available as the source-grounded fallback for absent, stale, incomplete,
unavailable, or damaged runtime state.

Public bounds are ten results per page, graph depth four, and 4096 source-text
characters in a full read. Backend calls and SQLite execution have explicit
timeouts, while trace evidence remains in a bounded in-process cache.

## Tiered Family Operation

Hydrate a complete trust-admitted owner release:

```bash
scripts/aoa-kag-runtime-family \
  --stack-root "${AOA_STACK_ROOT}" \
  hydrate-owner \
  --family-root /path/to/verified-owner-subject-store \
  --trust-gate /path/to/owner-trust-gate.json \
  --owner owner-name
```

Hydrate a bounded candidate selection:

```bash
scripts/aoa-kag-runtime-family \
  --stack-root "${AOA_STACK_ROOT}" \
  hydrate-owner \
  --family-root /path/to/verified-owner-subject-store \
  --trust-gate /path/to/owner-trust-gate.json \
  --owner owner-name \
  --kind anchor \
  --range-prefix 0a
```

Activate a signed 24-owner composition only after every exact owner release is
current:

```bash
scripts/aoa-kag-runtime-family \
  --stack-root "${AOA_STACK_ROOT}" \
  activate-composition \
  --composition-root /path/to/verified-composition-subject-store \
  --trust-gate /path/to/composition-trust-gate.json
```

Inspect state or roll one owner back to its verified last-good family:

```bash
scripts/aoa-kag-runtime-family --stack-root "${AOA_STACK_ROOT}" status
scripts/aoa-kag-runtime-family \
  --stack-root "${AOA_STACK_ROOT}" \
  rollback-owner \
  --owner owner-name
```

These commands do not discover remote locations or perform network fetches.
The operator or artifact lifecycle supplies the already admitted subject
store. A corrupt local object, wrong owner, wrong source ref, wrong access
policy, revoked lifecycle, invalid signature state, or mismatched trust root
fails closed.

## Projection Operation

Build the bundle with `aoa-kag`, then materialize selected targets:

```bash
scripts/aoa-kag-runtime-projection \
  --bundle-dir /path/to/repo-self-bundle \
  --target all \
  --owner-scoped
```

The first owner-scoped run bootstraps every owner. For a later owner-local
corpus change, advance only the owners named by the verified change impact:

```bash
scripts/aoa-kag-runtime-projection \
  --bundle-dir /path/to/repo-self-bundle \
  --target all \
  --owner-scoped \
  --affected-owner aoa-kag
```

Verify the active projections against the same bundle:

```bash
scripts/aoa-kag-runtime-projection \
  --bundle-dir /path/to/repo-self-bundle \
  --target all \
  --owner-scoped \
  --check
```

Return all three targets to their mutually matching last-good projection:

```bash
scripts/aoa-kag-runtime-projection \
  --target all \
  --owner-scoped \
  --rollback
```

An affected-owner update is rejected when another owner's semantic canonical
input also changed, when owner membership or the embedding profile changed, or
when no full bootstrap exists. Distribution-only relocation may change delivery
identity while retaining the logical projection identity and therefore does
not force a semantic rebuild.

Measure the active retrieval routes:

```bash
scripts/aoa-kag-runtime-eval
```

The eval derives exact, filtered, lexical, and graph cases from the active
projection and reads curated semantic cases from
`config/repo-self-retrieval-eval.json`. It records recall, MRR, NDCG,
groundedness, graph evidence-chain completeness, graph advantage, latency, and
canonical identity/reference quality in
`receipts/<projection-digest>/retrieval-eval.json`. `--check` runs the same
measurement without updating runtime receipts.

Embedding, Qdrant, and Neo4j endpoints are host-local by default and can be
selected through the corresponding `AOA_KAG_*` environment variables. Neo4j
credentials come from `AOA_KAG_NEO4J_*`, `AOA_RAG_NEO4J_*`, `NEO4J_AUTH`, or
the deployed `Secrets/Configs/stack.env`.
Receipts expose endpoint-independent identities, counts, durations, retrieval
metrics, and output handles.

## Ownership

Each repository owns its canonical `/kag` records. `aoa-kag` owns their common
language, builders, corpus/distribution identity, federation, release
manifests, and retrieval bundle. `abyss-machine` owns artifact signing,
verification, promotion, subject-store admission, retention, and revocation.
`abyss-stack` owns the local CAS, mutable owner/composition state, projections,
cutover, last-good rollback coordinates, and runtime receipts described here.
`aoa-kag-mcp` remains a read-only access plane and does not hydrate, promote,
sign, revoke, or mutate any of those surfaces.

The existing `aoa-kag` and `tos-source` mirrors remain the advisory-only
inspection route for `/kag/*` and the source-owned `Tree-of-Sophia` handoff:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
```
