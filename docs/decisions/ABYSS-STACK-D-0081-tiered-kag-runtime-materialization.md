# Tiered KAG Runtime Materialization

- Decision ID: ABYSS-STACK-D-0081
- Status: accepted
- Date: 2026-07-18
- Owner surface: `mechanics/federation-seams/parts/kag-seam/`

## Index Metadata

- Original date: 2026-07-18
- Surface classes: runtime/storage/federation
- Stack lanes: runtime lane/federation lane/MCP lane
- Mechanic parents: federation-seams
- Guard families: artifact trust/source-runtime boundary
- Posture: accepted rationale

## Context

The canonical KAG owners must be able to externalize cold content-addressed
objects without making an artifact locator, an artifact store, a runtime
database, or MCP the new source of truth. The previous stack route accepted one
complete retrieval bundle and rebuilt mutable exact, vector, and graph
projections from it. That route did not model owner-family admission, local CAS
reuse, partial hydration, last-good owner state, or a 24-owner composition
cutover.

## Options considered

- Keep complete owner corpora in Git and continue rebuilding one full runtime
  bundle.
- Let MCP fetch cold shards directly from artifact locations during queries.
- Admit signed owner-family releases through the machine trust plane, hydrate
  them into a stack-owned local CAS, activate only complete verified owner
states and compositions, and keep MCP as a bounded read-only adapter.

## Decision

`abyss-stack` owns a local tiered KAG materializer under
`Knowledge/kag/repo-self/`. It accepts only exact-commit owner-family releases
and OS compositions already admitted by the `abyss-machine` artifact trust
gate. It verifies identities and object bytes, reuses content-addressed objects,
keeps candidate, current, and last-good owner state separate, and activates an
OS composition only when all 24 exact owner states are complete and match.

Selective hydration may prepare a candidate but cannot report it as complete.
Network discovery and unbounded fetches do not occur inside MCP requests.
Exact, vector, graph, embedding, and query-cache state remains regenerable
runtime projection state and never becomes canonical KAG truth.

The promoted projection topology is owner-scoped. SQLite remains one physical
database but advances by copying last-good state and transactionally replacing
only affected owner rows, FTS entries, and relations or external references
touching them. Qdrant uses one immutable content-addressed collection per
owner. Neo4j uses immutable owner-node slices plus directional owner-pair
relation and external-reference slices. Current state maps select the admitted
slices, and unchanged owners are reused without rebuild.

Vector fan-out embeds a query once and merges bounded per-owner results. Graph
traversal is constrained to the current owner and relation slice digests.
Coordinated rollback is allowed only when exact, vector, and graph last-good
states name the same projection, bundle, and federation identities; a mixed
generation fails closed. Physical relocation or repacking changes distribution
identity but does not by itself change semantic projection identity.

## Rationale

This route keeps logical KAG identity and delivery topology separate. The
machine owner remains responsible for signature, revocation, retention, and
subject-store admission; the stack is responsible only for local
materialization, cache reuse, cutover, degradation, and rollback. MCP can
surface delivery identity and degradation without gaining storage, mutation,
or proof authority.

## Consequences

- Positive: unchanged shard objects are reused across releases and owner
  updates can remain owner-local.
- Positive: partial, unavailable, corrupted, revoked, and mismatched states are
  explicit and cannot silently become complete runtime state.
- Positive: last-good owner and composition coordinates remain available for
  bounded rollback.
- Positive: an ordinary owner corpus change rewrites only that owner's exact
  rows and vector slice plus graph slices touching the owner; unaffected
  owner projections remain stable.
- Positive: one coordinated rollback receipt proves exact, vector, and graph
  returned to one mutually matching last-good generation.
- Tradeoff: operators must stage and trust-admit owner releases before the
  stack can hydrate them.
- Tradeoff: the first owner-scoped projection is still a full bootstrap, and
  owner membership, schema, canonicalization, or embedding-profile changes may
  still require a full rebuild.
- Tradeoff: content-addressed remote slices require explicit retention so the
  current and last-good state maps never point at reclaimed collections.
- Follow-up: selective projection, retention, and cross-owner relation receipts
  must stay aligned with the owner impact emitted by the materializer.

## Source surfaces

- `DESIGN.md`
- `docs/runtime/ARCHITECTURE.md`
- `docs/runtime/STORAGE_LAYOUT.md`
- `mechanics/federation-seams/parts/kag-seam/README.md`
- `mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md`
- `mechanics/federation-seams/parts/kag-seam/aoa_kag_runtime_projection.py`
- `mechanics/federation-seams/parts/kag-seam/kag_runtime/distribution.py`
- `mechanics/federation-seams/parts/kag-seam/kag_runtime/exact.py`
- `mechanics/federation-seams/parts/kag-seam/kag_runtime/vector.py`
- `mechanics/federation-seams/parts/kag-seam/kag_runtime/graph.py`
- `mcp/services/aoa-kag-mcp/DESIGN.md`
- `mcp/services/aoa-kag-mcp/docs/BOUNDARIES.md`

## Follow-up route

Revisit this decision if KAG access classes split into separate public and
restricted trust domains, if the artifact owner changes its admission ABI, or
if a runtime projection is proposed as canonical owner truth.
