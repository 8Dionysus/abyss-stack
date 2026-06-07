# ToS Corpus MCP Design

## Purpose

Expose the whole `Tree-of-Sophia/ToS/` corpus index to agents and graph-review
surfaces without copying ToS-owned meaning into `abyss-stack`.

## Shape

`Tree-of-Sophia` publishes a checked derived resource:

```text
ToS/derived-exports/tos_corpus_index.min.json
```

`tos-corpus-mcp` reads that file and serves bounded packets:

- `status`: freshness, path, counts, and available graph views
- `summary`: compact whole-corpus map
- `search`: text search over nodes, resources, manifests, branches, and views
- `graph_view`: one named view such as topology, layers, route, provenance, promotion, or diff
- `node`: one indexed ToS node
- `relation_pack`: one indexed relation pack and its edges

## Authority

The MCP package owns access behavior only. It does not own source witnesses,
canon, relation packs, research packets, contracts, derived exports, or graph
meaning. Runtime projection stores such as Neo4j remain caches and query
surfaces.
