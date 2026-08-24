# aoa-kag-mcp Boundaries

| Surface | Owner |
| --- | --- |
| authored repository meaning and canonical repo-self records | source repository and its `kag/` home |
| common corpus/distribution identity, schema, provenance, retrieval, federation, freshness, and ABI contracts | `aoa-kag` |
| artifact signature, revocation, lifecycle, subject-store, and access admission | `abyss-machine` |
| local CAS, owner/composition candidate-current-last-good state, owner-local SQLite/FTS updates, Qdrant owner collections, Neo4j owner/owner-pair slices, coordinated cutover/rollback, and runtime receipts | `abyss-stack` `kag-seam` |
| five MCP tools, resources, transports, and service validation | `aoa-kag-mcp` |
| native subject indexes in session memory, connectors, and other organs | their source owners |

The MCP service is a read-only application adapter. It reports owner routes and
corpus, distribution, release, projection, freshness, and degradation state
while source generation, artifact admission, hydration, index refresh, graph
materialization, and subject-specific operations remain on their owner
lifecycles. It cannot turn a partial hydration into a complete result and
cannot fetch or promote artifacts as a side effect of a read.

`AOA_KAG_ARTIFACT_ROOT` is only a source-managed consumer binding. The
`abyss-machine` artifact owner still decides allow/warn/deny/
manual_review_required/unknown, and `abyss-stack` does not rewrite that
verdict.

An `aoa-kag://` result is an addressable evidence route. Authored meaning is
changed at the returned source owner, and runtime state is operated through the
stack-owned projection route.
