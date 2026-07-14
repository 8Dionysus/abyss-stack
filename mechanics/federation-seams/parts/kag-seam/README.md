# KAG Runtime Seam

This part materializes the OS Abyss repo-self KAG bundle and serves one
storage-neutral query application port.

`aoa-kag` supplies a manifest-bound bundle of owners, nodes, relations,
external references, and retrieval documents. `abyss-stack` verifies that
bundle and projects it into SQLite/FTS, Qdrant, and Neo4j through
`scripts/aoa-kag-runtime-projection`. `scripts/aoa-kag-runtime-eval` measures
exact, filtered, lexical, vector, hybrid, and graph retrieval against the
active projection and writes a projection-bound receipt.

`kag_runtime.application.KagApplication` composes those stores with canonical
repo-local reads behind `discover`, `search`, `read`, `traverse`, and
`explain`. It reports the route actually used and falls back to owner records
when runtime state is missing, stale, or damaged.

Runtime state and receipts live under
`${AOA_STACK_ROOT}/Knowledge/kag/repo-self/`. The complete operator and storage
contract is [KAG_RUNTIME_SEAM.md](docs/KAG_RUNTIME_SEAM.md).
