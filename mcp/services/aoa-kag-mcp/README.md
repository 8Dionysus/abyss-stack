# aoa-kag-mcp

`aoa-kag-mcp` is the read-only agent access plane for repository knowledge
across OS Abyss.

## Operating Card

| Field | Route |
| --- | --- |
| service owner | `abyss-stack` |
| canonical records | each repository's `kag/` home |
| common contract | `aoa-kag` schemas, federation, provenance, and provider map |
| runtime reads | `kag-seam` application port over SQLite/FTS, Qdrant, and Neo4j |
| transports | portable stdio and authenticated host-local Streamable HTTP |

## Agent Surface

| Tool | Use |
| --- | --- |
| `kag_discover` | inspect owners, record classes, strategies, freshness, projections, and bounds |
| `kag_search` | retrieve through `auto`, exact, lexical, semantic, hybrid, or graph strategy |
| `kag_read` | read one returned `aoa-kag://` record, document, source, schema, projection, or evidence resource |
| `kag_traverse` | follow owner-qualified relations with bounded depth and path evidence |
| `kag_explain` | inspect the route, adapters, degradation, projection, and evidence for a trace |

Results preserve qualified owner identity, source anchors, provenance, trust,
freshness, access, projection identity, and resource links. Detail levels and
cursor pagination keep context bounded.

Runtime projections accelerate retrieval. Canonical repo-local queries remain
available when a projection is absent, stale, damaged, or incomplete, and the
result reports the route actually used.

Canonical fallback reads the tracked portable-v3 family manifest and bounded
JSONL shards directly; the seven v2 monolith paths remain logical compatibility
coordinates and are not required to exist in Git.

The current protocol uses five static tools and nine resource shapes. New
record kinds and owner-specific domain catalogs enter through capabilities and
data instead of adding tool names.

See [DESIGN](DESIGN.md), [BOUNDARIES](docs/BOUNDARIES.md), and
[THREAT_MODEL](docs/THREAT_MODEL.md) for the owner and transport contracts.
