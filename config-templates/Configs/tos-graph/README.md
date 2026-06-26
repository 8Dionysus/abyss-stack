# tos-graph config

This directory stores the public-safe config template for the ToS graph helper.
The helper reads the corpus index, materialized philosophy graph projection,
and source-side review audit packets published by Tree of Sophia.

Bootstrapped runtime path:

- `${AOA_STACK_ROOT}/Configs/tos-graph/config.yaml`

Runtime-only secret-bearing env file:

- `${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env`

Runtime stack-env mount used for Neo4j auth fallback:

- `${AOA_STACK_ROOT}/Configs/stack.env`

The helper stays localhost-only, read-first, and projection-only in this slice.
Keep canonical ToS authority in `Tree-of-Sophia`; do not place credentials,
write-enable defaults, or machine-local paths in this template. When explicit
`TOS_GRAPH_NEO4J_*` overrides are absent, the service may reuse `NEO4J_AUTH`
from the mounted runtime `stack.env` so graph projection can remain
operator-local without duplicating secrets into git.

Operator entrypoint:

```bash
scripts/tos-up
scripts/aoa-tos-graph
```

Those commands start the `curation` profile, wait for the localhost health
endpoint, and open the switchable philosophy/corpus graph workbench when a
desktop opener is available.
