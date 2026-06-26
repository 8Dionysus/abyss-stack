# ToS Corpus MCP Design

## Purpose

Expose the whole `Tree-of-Sophia/ToS/` corpus index and the materialized
philosophy graph projection to agents and graph-review surfaces without copying
ToS-owned meaning into `abyss-stack`.

## Shape

`Tree-of-Sophia` publishes a checked derived resource:

```text
ToS/derived-exports/tos_corpus_index.min.json
ToS/derived-exports/philosophy_graph_projection.min.json
```

`tos-corpus-mcp` reads that file and serves bounded packets:

- `status`: freshness, path, counts, and available graph views
- `summary`: compact whole-corpus map
- `search`: text search over nodes, resources, manifests, branches, and views
- `graph_view`: one named view such as topology, layers, route, provenance, promotion, or diff
- `node`: one indexed ToS node
- `relation_pack`: one indexed relation pack and its edges
- `philosophy_status`: graph projection path, counts, views, layers, and boundary
- `philosophy_view`: one materialized philosophy graph view
- `philosophy_node`: one projected philosophy node and related edges
- `philosophy_neighborhood`: local projected graph context
- `philosophy_packet`: compact agent packet with optional search and view context

## Authority

The MCP package owns access behavior only. It does not own source witnesses,
canon, relation packs, research packets, contracts, derived exports, or graph
meaning. Runtime projection stores such as Neo4j remain caches and query
surfaces.
