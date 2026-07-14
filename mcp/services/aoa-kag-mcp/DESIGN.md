# aoa-kag-mcp Design

## Purpose

`aoa-kag-mcp` turns the `aoa-kag` provider map into MCP resources, tools, and
prompts for agents.

## Source Flow

1. `aoa-kag/manifests/local_kag_readiness.json` names direct repos and OS
   surfaces.
2. Repo-local `kag/` homes carry manifest, node, edge, index, projection, and
   receipt records.
3. `aoa-kag/generated/local_kag_provider_map.min.json` composes the compact
   access packet.
4. `aoa-kag-mcp` reads that packet and returns bounded access-plane views.

## Runtime Shape

The service remains read-only. Stdio is the portable default, while
`ABYSS-STACK-D-0077` permits an explicitly selected authenticated loopback
shared HTTP owner. Both routes keep provider-map reads cheap, use explicit
source-return handles, and leave graph databases, vector stores, embedding
caches, and live indexing to their runtime-owned contracts.

## Interface

Resources expose exact packet surfaces. Tools return typed JSON packets over
provider status, canonical repository index families,
owner-native domain index catalogs, repo-local coverage, freshness,
source-return routes, registry slices, and simple composition search. Prompts
guide agents through provider records, source-return routes, and repo-local
source surfaces before making meaning claims.
