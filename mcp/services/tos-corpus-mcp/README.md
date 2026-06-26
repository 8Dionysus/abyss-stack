# ToS Corpus MCP

`tos-corpus-mcp` exposes the checked Tree of Sophia corpus index through a
stack-owned MCP access plane.

It reads:

- `Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json`
- `Tree-of-Sophia/ToS/derived-exports/philosophy_graph_projection.min.json`

It returns:

- corpus status and counts
- whole-corpus summary
- graph-view packets
- resource and node search
- relation-pack packets
- philosophy graph status, views, layers, nodes, edges, neighborhoods, review
  packets, snapshot fingerprints, post-planting audit packets, and compact
  packets

## Boundary

Tree of Sophia owns the corpus and philosophy graph resources. `abyss-stack`
owns this MCP access plane, runtime projection, and visualization support. MCP
packets help agents review and navigate the corpus and projected philosophy
graph; they do not become ToS source truth.

## Local Checks

```bash
python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py
python -m pytest mcp/services/tos-corpus-mcp/tests -q
```
