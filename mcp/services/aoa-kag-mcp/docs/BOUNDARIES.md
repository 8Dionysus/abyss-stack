# aoa-kag-mcp Boundaries

| Surface | Owner |
| --- | --- |
| authored repository meaning and canonical repo-self records | source repository and its `kag/` home |
| common identity, schema, provenance, retrieval, federation, freshness, and ABI contracts | `aoa-kag` |
| mutable SQLite, Qdrant, Neo4j, cutover, retention, and runtime receipts | `abyss-stack` `kag-seam` |
| five MCP tools, resources, transports, and service validation | `aoa-kag-mcp` |
| native subject indexes in session memory, connectors, and other organs | their source owners |

The MCP service is a read-only application adapter. It reports owner routes and
projection state while source generation, index refresh, graph materialization,
and subject-specific operations remain on their owner lifecycles.

An `aoa-kag://` result is an addressable evidence route. Authored meaning is
changed at the returned source owner, and runtime state is operated through the
stack-owned projection route.
