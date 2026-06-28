# aoa-kag-mcp

`aoa-kag-mcp` exposes the OS Abyss KAG provider map through a read-only MCP
access plane.

## Operating Card

| Field | Route |
| --- | --- |
| owner | `abyss-stack` MCP service package |
| source authority | `aoa-kag` schema, readiness, generated provider map, and repo-local `kag/` homes |
| primary input | `aoa-kag/generated/local_kag_provider_map.min.json` |
| resources | provider map, readiness matrix, provider manifests, provider records |
| tools | provider lookup, status, freshness, source-return lookup, registry slice, composition slice, validation status |
| prompts | bounded provider query, source-return summary, cross-repo relation preview, runtime handoff brief |

The service reads compact provider records and source-return handles. It does
not build embeddings, write graph state, mutate provider homes, run validators
as hidden side effects, or replace source-owner docs.
