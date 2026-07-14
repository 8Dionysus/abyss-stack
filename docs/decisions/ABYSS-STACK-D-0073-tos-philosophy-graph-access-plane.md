# ToS Philosophy Graph Access Plane

- Decision ID: ABYSS-STACK-D-0073
- Status: accepted
- Date: 2026-06-25
- Owner surface: `mcp/services/tos-corpus-mcp/`

## Index Metadata

- Original date: 2026-06-25
- Surface classes: MCP access plane, runtime graph projection
- Stack lanes: MCP services, Tree of Sophia access, tos-graph
- Mechanic parents: federation-seams
- Guard families: read-only access plane, source-structure, projection-only cache
- Posture: accepted ToS philosophy graph access-plane rationale

## Context

Tree of Sophia now publishes a materialized philosophy graph projection derived
export. Agents, the localhost graph UI, and Neo4j projection cache need access
to that graph without making `abyss-stack` author ToS philosophy meaning.

The existing `tos-corpus-mcp` package already owns the read-only MCP route for
ToS-derived graph context. The open choice is whether the philosophy graph
projection should become a separate MCP package or remain in that package as a
clearly named packet family.

## Options considered

- Keep philosophy graph access as direct file reads only.
- Create a separate `tos-philosophy-graph-mcp` package.
- Extend `tos-corpus-mcp` with explicit `tos_philosophy_graph_*` tools and
  `tos-philosophy://` resources.

## Decision

Extend `tos-corpus-mcp` with explicit philosophy graph tools and resources.

The package reads:

```text
Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json
Tree-of-Sophia/ToS/derived-exports/philosophy_graph_projection.min.json
```

It exposes the corpus packet family and a separate philosophy graph packet
family: status, views, view, node, neighborhood, search, compact packet, and
review prompt.

## Rationale

The philosophy graph projection is a ToS-derived graph export, not a new
runtime owner. Keeping it in the existing ToS MCP access-plane package avoids a
premature second service while preserving the semantic split through tool names,
resource URI schemes, docs, validators, and tests.

This route stays smaller than a new package and still leaves a clean escape
hatch: if philosophy graph tools become operationally large, they can split
later behind the same ToS authority boundary.

## Consequences

- Positive: agents get one ToS MCP access plane with distinct corpus and
  philosophy graph packet families.
- Tradeoff: the package name remains `tos-corpus-mcp` until a later rename or
  split is justified by scale.
- Follow-up: revisit package split only if philosophy graph behavior becomes a
  large runtime surface rather than a bounded read-only packet family.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/README.md`
- `mcp/services/README.md`
- `mcp/services/tos-corpus-mcp/AGENTS.md`
- `mcp/services/tos-corpus-mcp/DESIGN.md`
- `mcp/services/tos-corpus-mcp/README.md`
- `mcp/services/tos-corpus-mcp/src/tos_corpus_mcp/core.py`
- `mcp/services/tos-corpus-mcp/src/tos_corpus_mcp/server.py`
- `config-templates/Services/tos-graph/app/philosophy_reader.py`
- `config-templates/Services/tos-graph/app/main.py`
- `config-templates/Services/tos-graph/app/projector.py`
- `config-templates/Services/tos-graph/app/neo4j_store.py`
- `config-templates/Services/tos-graph/app/ui.py`
- `mechanics/federation-seams/parts/tos-graph/docs/TOS_GRAPH_CURATION.md`

## Follow-up route

Use the corpus service `AGENTS.md`, parent MCP route, ToS graph owner route,
and root validation route. Those active owners retain the exact commands.

Use Tree of Sophia validators before changing either ToS-derived export shape
that this access plane reads.
