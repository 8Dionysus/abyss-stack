# KAG Runtime Projection

This part materializes the OS Abyss repo-self KAG bundle for runtime search and
graph traversal.

`aoa-kag` supplies a manifest-bound bundle of owners, nodes, relations,
external references, and retrieval documents. `abyss-stack` verifies that
bundle and projects it into SQLite/FTS, Qdrant, and Neo4j through
`scripts/aoa-kag-runtime-projection`.

Runtime state and receipts live under
`${AOA_STACK_ROOT}/Knowledge/kag/repo-self/`. The complete operator and storage
contract is [KAG_RUNTIME_SEAM.md](docs/KAG_RUNTIME_SEAM.md).
