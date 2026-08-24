# aoa-kag-mcp Design

## System Flow

1. Each repository publishes its canonical repo-self family under `kag/`.
2. `aoa-kag` validates owner identity, publishes content-addressed owner-family
   releases, composes the exact membership-bound federation identity, and
   publishes the MCP capability and result contracts.
3. `abyss-machine` verifies signatures, provenance, lifecycle, access policy,
   and subject-store identity for owner releases and OS compositions.
4. `abyss-stack` hydrates admitted objects into a local CAS, activates only
   complete matching owner/composition state, and materializes exact, vector,
   and graph projections as owner-local exact updates, Qdrant owner
   collections, and Neo4j owner/owner-pair slices.
5. The `kag-seam` application port composes canonical and runtime adapters into
   storage-neutral KAG operations.
6. `aoa-kag-mcp` maps those operations to MCP tools and `aoa-kag://` resources.

## Application Port

The public behavior is `discover`, `search`, `read`, `traverse`, and `explain`.
Storage names stay behind the port. Every response states the strategy and
adapters actually used, corpus/distribution/release identity, projection
identity, freshness, degradation, and evidence links.

Canonical repo-local reads are the source-grounded fallback. Runtime SQLite,
Qdrant, and Neo4j are replaceable projections. A backend outage changes route
quality and capability state rather than the MCP tool ABI.

For a v4 canonical family, `AOA_KAG_ARTIFACT_ROOT` is the explicit consumer
configuration seam for the owner-approved cold CAS. The adapter passes the
root to `load_family` and rejects shadow-Git fallback for that read; source
ownership, artifact admission, and runtime activation remain separate routes.

Owner-family hydration and prefetch are explicit materializer operations.
Selective hydration remains candidate state until the complete release is
present and verified. MCP does not discover mirrors, fetch unbounded packs,
activate compositions, or promote runtime state during a read.

## Context Shape

Capability discovery is compact. Search and traversal return bounded envelopes
with cursor pagination. `compact`, `summary`, and `full` detail levels move
source text, score detail, and evidence expansion behind explicit requests.

Nine resource shapes address capabilities, owner manifests, records,
documents, source anchors, source text, evidence traces, schemas, and runtime
projection state. The current agent scenarios gained no measurable value from
MCP prompts, Tasks, or Apps, so the access plane publishes none.

## Transport

Stdio is the portable process-local route. Streamable HTTP is an
owner-specific read contour protected by the `aoa-kag` read bearer, scope,
client identity, Host validation, Origin validation, fixed per-call bounds,
and backend timeouts. Both transports expose the same tools, resources, and
result contracts.
