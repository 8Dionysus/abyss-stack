# KAG Query Application Port

- Decision ID: ABYSS-STACK-D-0079
- Status: accepted
- Date: 2026-07-14
- Owner surface: `mechanics/federation-seams/parts/kag-seam/`

## Index Metadata

- Original date: 2026-07-14
- Surface classes: KAG application port, MCP access plane, runtime retrieval
- Stack lanes: federation seam, MCP services, runtime knowledge
- Mechanic parents: federation-seams
- Guard families: owner-qualified provenance, canonical fallback, bounded context, loopback transport security
- Posture: accepted KAG query and MCP access rationale

## Context

`ABYSS-STACK-D-0075` exposed a static provider map, while
`ABYSS-STACK-D-0076` materialized exact, vector, and graph stores. Agents still
needed one operational contract for discovery, retrieval, addressed reads,
relation traversal, evidence explanation, and honest degradation across those
owners and projections.

Laboratory scenarios covered repeated repository shapes, owner collisions,
unknown kinds, conflicting assertions, changing source trees, missing and
damaged projections, graph cycles, private records, hostile indexed text,
multiple MCP clients, and both supported transports.

## Options considered

1. Keep the static provider-map tools and add one operation for each new query.
2. Publish backend-specific SQLite, Qdrant, and Neo4j tools.
3. Place a storage-neutral KAG application port below a compact MCP surface.

## Decision

Choose option 3.

`kag-seam` owns a read-only application port with five operations: discover,
search, read, traverse, and explain. It composes canonical repo-local queries,
SQLite/FTS, Qdrant, and Neo4j while returning the route, projection state,
degradation, provenance, access, and evidence actually used.

`aoa-kag-mcp` exposes the same five operations as static read-only tools plus
nine `aoa-kag://` resource shapes. New owners and record kinds extend
capabilities and data. Stdio and authenticated host-local Streamable HTTP share
the same contract.

## Rationale

The application port keeps storage replacement and degradation below the agent
ABI. Five stable verbs gave the best task success and context cost in the
laboratory compared with a large operation catalog and progressive tool-name
discovery. Resources and detail levels provided sufficient progressive
disclosure; prompts, Tasks, and Apps added no measured value to the current
read-only scenarios.

Canonical fallback preserves source-grounded use during projection drift.
Qualified identities and access filtering keep same-named surfaces and private
records inside their owners. Loopback bearer authentication, Host and Origin
validation, bounded requests, and backend timeouts fit the shared
single-operator deployment profile.

## Consequences

- Agents get one stable retrieval protocol across every repo-local KAG home.
- Runtime backends can change without adding public tools.
- Every result exposes owner, source, freshness, projection, route, and trace.
- The provider map remains a validated capability and owner-routing input
  instead of the public operation catalog.
- A future remote or multi-user profile owns explicit identity, scopes, quotas,
  rates, and deployment isolation.

## Source surfaces

- `mechanics/federation-seams/parts/kag-seam/kag_runtime/application.py`
- `mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md`
- `mcp/services/aoa-kag-mcp/`
- `mcp/services/_shared/http_auth.py`
- `systemd/user/aoa-mcp-http@.service`
- `aoa-kag:schemas/kag-mcp-capabilities.schema.json`
- `aoa-kag:schemas/kag-mcp-result.schema.json`
- `aoa-kag:generated/local_kag_provider_map.min.json`

## Follow-up route

Runtime refresh actions enter the agent surface through their owner lifecycle
only when a real operational scenario and authorization contract justify them.
