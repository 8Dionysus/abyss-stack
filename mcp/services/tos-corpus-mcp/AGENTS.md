# AGENTS.md

## Applies to

This card applies to `mcp/services/tos-corpus-mcp/`.

## Role

`tos-corpus-mcp` is a thin MCP access plane for the Tree of Sophia corpus index
and related derived graph exports. It exposes ToS-owned corpus resources,
philosophy graph projection packets, and search helpers without moving authored
ToS meaning into `abyss-stack`.

## Operating Card

| Field | Route |
| --- | --- |
| role | MCP access plane for ToS corpus and philosophy graph derived exports |
| input | `Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json`; `Tree-of-Sophia/ToS/derived-exports/philosophy_graph_projection.min.json` |
| output | corpus status, summary, resource, search, graph-view, node, relation-pack packets; philosophy graph status, view, node, neighborhood, and compact packets |
| owner | `mcp/services/tos-corpus-mcp/AGENTS.md` for access-plane behavior; Tree of Sophia owns the derived resources |
| next route | ToS resource -> MCP packet -> runtime graph/UI/review route |
| tools | `tos_corpus_mcp.core`, `tos_corpus_mcp.server`, `scripts/validate_tos_corpus_mcp.py` |
| check | on-demand package validation route in `VALIDATION.md` |

## Boundaries

- Keep `Tree-of-Sophia` canonical for source-home branches, philosophy source
  refs, nodes, relation packs, witnesses, research packets, contracts, corpus
  index, and graph projection export.
- Keep `abyss-stack` responsible only for MCP, runtime access, graph projection,
  UI, cache, and service behavior.
- Do not make MCP output stronger than the ToS exports it reads.
- MCP packets are navigation aids, not source truth.
- Do not add writeback here. A future write route must be ToS-validator-gated
  and separately reviewed.
- Keep HTTP authentication owner-specific:
  `TOS_CORPUS_MCP_READ_BEARER_TOKEN`,
  `tos-corpus-mcp-read-bearer-token`, `mcp:tos-corpus:read`, and
  `aoa-loopback-codex:tos-corpus:read`.
- Do not add `tos-corpus` to the default owner bundle until the deployed
  workspace wrapper and grounded live canary exist.

## Validation

Use the on-demand validation route in `VALIDATION.md` for the exact focused procedure.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For parent MCP route changes, also use the on-demand validation route in `VALIDATION.md`.
