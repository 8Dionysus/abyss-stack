# tos-graph config

This directory stores the public-safe config template for the corpus-index ToS
graph helper.

Bootstrapped runtime path:

- `${AOA_STACK_ROOT}/Configs/tos-graph/config.yaml`

Runtime-only secret-bearing env file:

- `${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env`

Runtime stack-env mount used for Neo4j auth fallback:

- `${AOA_STACK_ROOT}/Configs/stack.env`

The helper stays corpus-index-first, localhost-only, and read-first in this slice.
Keep canonical ToS authority in `Tree-of-Sophia`; do not place credentials,
write-enable defaults, or machine-local paths in this template. When explicit
`TOS_GRAPH_NEO4J_*` overrides are absent, the service may reuse `NEO4J_AUTH`
from the mounted runtime `stack.env` so corpus projection can remain
operator-local without duplicating secrets into git.
