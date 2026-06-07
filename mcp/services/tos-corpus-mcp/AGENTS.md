# AGENTS.md

## Applies to

This card applies to `mcp/services/tos-corpus-mcp/`.

## Role

`tos-corpus-mcp` is a thin MCP access plane for the Tree of Sophia corpus index.
It exposes ToS-owned corpus resources, graph-view packets, and search helpers
without moving authored ToS meaning into `abyss-stack`.

## Operating Card

| Field | Route |
| --- | --- |
| role | MCP access plane for the ToS whole-corpus index |
| input | `Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json` |
| output | status, summary, resource, search, graph-view, node, and relation-pack packets |
| owner | `mcp/services/tos-corpus-mcp/AGENTS.md` for access-plane behavior; Tree of Sophia owns the corpus resource |
| next route | ToS resource -> MCP packet -> runtime graph/UI/review route |
| tools | `tos_corpus_mcp.core`, `tos_corpus_mcp.server`, `scripts/validate_tos_corpus_mcp.py` |
| check | `python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py`, `python -m pytest mcp/services/tos-corpus-mcp/tests -q` |

## Boundaries

- Keep `Tree-of-Sophia` canonical for source-home branches, nodes, relation
  packs, witnesses, research packets, contracts, and derived corpus index.
- Keep `abyss-stack` responsible only for MCP, runtime access, graph projection,
  UI, cache, and service behavior.
- Do not make MCP output stronger than the ToS index it reads.
- MCP packets are navigation aids, not source truth.
- Do not add writeback here. A future write route must be ToS-validator-gated
  and separately reviewed.

## Validation

Run:

```bash
python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py
python -m pytest mcp/services/tos-corpus-mcp/tests -q
```

For parent MCP route changes, also run:

```bash
python scripts/validate_nested_agents.py
```
