# ToS Corpus MCP

`tos-corpus-mcp` exposes the checked Tree of Sophia corpus index through a
stack-owned MCP access plane.

It reads:

- `Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json`

It returns:

- corpus status and counts
- whole-corpus summary
- graph-view packets
- resource and node search
- relation-pack packets

## Boundary

Tree of Sophia owns the corpus resource. `abyss-stack` owns this MCP access
plane, runtime projection, and visualization support. MCP packets help agents
review and navigate the corpus; they do not become ToS source truth.

## Local Checks

```bash
python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py
python -m pytest mcp/services/tos-corpus-mcp/tests -q
```
