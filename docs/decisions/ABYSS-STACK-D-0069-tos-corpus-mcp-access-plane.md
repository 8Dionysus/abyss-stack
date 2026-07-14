# ToS Corpus MCP Access Plane

- Decision ID: ABYSS-STACK-D-0069
- Status: accepted
- Date: 2026-06-13
- Owner surface: `mcp/services/tos-corpus-mcp/`

## Index Metadata

- Original date: 2026-06-13
- Surface classes: MCP access plane, federation/read-model
- Stack lanes: MCP services, Tree of Sophia access
- Mechanic parents: federation-seams
- Guard families: read-only access plane, source-structure
- Posture: accepted ToS corpus access-plane rationale

## Context

Tree of Sophia now has a checked whole-corpus derived index that can support
agent navigation, graph review, search, and runtime projection without making
`abyss-stack` author ToS meaning.

Agents and localhost graph surfaces need a stable way to inspect the corpus
index. Direct file reads are possible, but they require each agent to rediscover
index shape, authority boundaries, and graph-view packet conventions.

## Options considered

- Keep ToS corpus navigation as direct file reads only.
- Fold ToS corpus packets into an existing AoA MCP service.
- Add a distinct `tos-corpus-mcp` package in `abyss-stack` that reads the
  ToS-owned derived index and serves bounded read-only packets.

## Decision

Choose the distinct `tos-corpus-mcp` package.

The package reads `Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json`
and exposes status, summary, search, resource, node, graph-view, relation-pack,
and review-prompt routes.

It is an access plane only. `Tree-of-Sophia` owns corpus resources, witnesses,
relation packs, contracts, and derived index generation. `abyss-stack` owns the
MCP package, runtime projection, UI, and cache behavior that consume that
index.

## Rationale

A separate MCP service keeps the owner split visible. Agents can ask for
bounded ToS corpus context through MCP without treating stack code, Neo4j, or a
localhost UI as stronger than the ToS source index.

This also avoids overloading session-memory, memo, evals, or decisions MCP
services with ToS-specific graph packets. Each access plane stays named by the
owner truth it routes to.

## Consequences

- Positive: agents get a small, reviewable ToS corpus access route with clear
  authority notes and fixed resources/tools.
- Tradeoff: the service depends on the ToS derived index being present and
  fresh; missing index state is reported rather than reconstructed silently.
- Follow-up: any writeback, promotion, or source-edit route must be
  Tree-of-Sophia-validator-gated and separately reviewed.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/tos-corpus-mcp/AGENTS.md`
- `mcp/services/tos-corpus-mcp/DESIGN.md`
- `mcp/services/tos-corpus-mcp/README.md`
- `mcp/services/tos-corpus-mcp/src/tos_corpus_mcp/core.py`
- `mcp/services/tos-corpus-mcp/src/tos_corpus_mcp/server.py`
- `config-templates/Services/tos-graph/app/corpus_reader.py`
- `config-templates/Services/tos-graph/app/main.py`
- `config-templates/Services/tos-graph/app/projector.py`

## Follow-up route

Use the service-local `AGENTS.md`, parent MCP route, and root validation route.
Exact commands remain with those active owners.

Use ToS repository validators before changing the corpus index shape that this
MCP service reads.
