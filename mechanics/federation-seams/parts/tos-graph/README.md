# ToS Graph

Routes `scripts/tos-up`, `scripts/aoa-tos-graph`, `tos_up.sh`, `aoa_tos_graph.sh`,
`docs/TOS_GRAPH_CURATION.md`, `config-templates/Services/tos-graph/frontend/`,
and `compose/modules/52-tos-graph.yml`.

Tree of Sophia owns authored meaning, the checked whole-corpus index, and the
materialized philosophy graph projection.
abyss-stack owns the local runtime graph projection service shape, including
the short `tos-up` localhost review workbench command, the read-only
scale-export API for external large-graph viewers, and the bundled Cosmos/Sigma
runtime graph lenses with layout families derived from ToS view contracts.

Current runtime contract:

- `/api/philosophy/contracts` exposes the light downstream contract packet
- `/api/philosophy/views/{view_id}` serves source-owned view subgraphs with
  `subgraph_contract` metadata
- `/api/philosophy/project/sync` refreshes the Neo4j projection when credentials
  are ready and reports scale-export row counts
- Neo4j, Cosmos, Sigma, and MCP access remain projection surfaces; ToS remains
  the source authority for meaning, source refs, graph layers, and canon status
