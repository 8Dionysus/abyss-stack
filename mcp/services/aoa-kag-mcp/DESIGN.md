# aoa-kag-mcp Design

## System Flow

1. Each repository publishes its canonical repo-self family under `kag/`.
2. `aoa-kag` validates owner identity, composes the federation bundle, and
   publishes the MCP capability and result contracts.
3. `abyss-stack` materializes exact, vector, and graph projections from that
   verified bundle.
4. The `kag-seam` application port composes canonical and runtime adapters into
   storage-neutral KAG operations.
5. `aoa-kag-mcp` maps those operations to MCP tools and `aoa-kag://` resources.

## Application Port

The public behavior is `discover`, `search`, `read`, `traverse`, and `explain`.
Storage names stay behind the port. Every response states the strategy and
adapters actually used, projection identity, freshness, degradation, and
evidence links.

Canonical repo-local reads are the source-grounded fallback. Runtime SQLite,
Qdrant, and Neo4j are replaceable projections. A backend outage changes route
quality and capability state rather than the MCP tool ABI.

## Context Shape

Capability discovery is compact. Search and traversal return bounded envelopes
with cursor pagination. `compact`, `summary`, and `full` detail levels move
source text, score detail, and evidence expansion behind explicit requests.

Nine resource shapes address capabilities, owner manifests, records,
documents, source anchors, source text, evidence traces, schemas, and runtime
projection state. The current agent scenarios gained no measurable value from
MCP prompts, Tasks, or Apps, so the access plane publishes none.

## Transport

Stdio is the portable process-local route. Streamable HTTP is a shared
single-operator loopback route protected by bearer authentication, Host and
Origin validation, fixed per-call bounds, and backend timeouts. Both
transports expose the same tools, resources, and result contracts.
