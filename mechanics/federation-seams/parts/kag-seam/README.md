# KAG Runtime Seam

This part admits tiered OS Abyss KAG owner families, materializes their
content-addressed objects and projections, and serves one storage-neutral query
application port.

`aoa-kag` supplies content-addressed owner-family releases, an OS composition,
and a manifest-bound retrieval bundle. `abyss-machine` owns signature,
revocation, access, and subject-store admission. `abyss-stack` verifies the
admitted family again while hydrating its local CAS through
`scripts/aoa-kag-runtime-family`, then projects verified records into
SQLite/FTS, Qdrant, and Neo4j through
`scripts/aoa-kag-runtime-projection`. `scripts/aoa-kag-runtime-eval` measures
exact, filtered, lexical, vector, hybrid, and graph retrieval against the
active projection and writes a projection-bound receipt.

The promoted projection route updates SQLite/FTS rows by affected owner, keeps
one content-addressed Qdrant collection per owner, and keeps immutable Neo4j
owner-node plus owner-pair relation/reference slices. Unchanged owners are
reused. Exact, vector, and graph roll back together only when their last-good
projection, bundle, and federation identities match.

`kag_runtime.application.KagApplication` composes those stores with canonical
repo-local reads behind `discover`, `search`, `read`, `traverse`, and
`explain`. It reports corpus, distribution, release, projection, freshness, and
degradation state and falls back to owner records when runtime state is
missing, stale, or damaged.

Runtime state and receipts live under
`${AOA_STACK_ROOT}/Knowledge/kag/repo-self/`. The complete operator and storage
contract is [KAG_RUNTIME_SEAM.md](docs/KAG_RUNTIME_SEAM.md).
