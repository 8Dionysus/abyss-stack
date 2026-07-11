# aoa-kag-mcp

`aoa-kag-mcp` exposes the OS Abyss KAG provider map through a read-only MCP
access plane.

## Operating Card

| Field | Route |
| --- | --- |
| owner | `abyss-stack` MCP service package |
| source authority | `aoa-kag` schema, readiness, generated provider map, and repo-local `kag/` homes |
| primary input | `aoa-kag/generated/local_kag_provider_map.min.json` |
| resources | provider map, readiness matrix, provider manifests and records, repository index families, typed repository indexes, domain index catalogs, repo-local coverage |
| tools | provider and generation lookup, repository index family and typed index lookup, domain catalog lookup, coverage, freshness, source-return, registry, composition, validation |
| prompts | bounded provider query, source-return summary, repo source-surface brief, cross-repo relation preview, runtime handoff brief |

The service reads compact provider records, generation routes, source/entity/
artifact/event index families, owner-native index catalogs, coverage rows, and
source-return handles. Graph databases, vector
stores, embedding caches, provider-home mutation, validator execution, and
source-owner meaning stay with their owning layers.
