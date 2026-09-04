# ToS Corpus MCP

`tos-corpus-mcp` exposes the checked Tree of Sophia corpus index through a
stack-owned MCP access plane.

It reads:

- `Tree-of-Sophia/ToS/derived-exports/tos_corpus_index.min.json`
- `Tree-of-Sophia/ToS/derived-exports/philosophy_graph_projection.min.json`

It returns:

- corpus status and counts
- whole-corpus summary
- graph-view packets
- resource and node search
- relation-pack packets
- philosophy graph status, contracts, views, layers, scale manifests, nodes,
  edges, neighborhoods, paths, review packets, snapshot fingerprints,
  post-planting audit packets, and compact packets

Every tool is a closed-world read:
`readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`, and
`openWorldHint=false`. The annotations mirror the implementation contract;
package tests and the validator inspect the published inventory.

## Boundary

Tree of Sophia owns the corpus and philosophy graph resources. `abyss-stack`
owns this MCP access plane, runtime projection, and visualization support. MCP
packets help agents review and navigate the corpus and projected philosophy
graph; they do not become ToS source truth.

Portable stdio remains the default. Optional loopback HTTP uses only:

- `TOS_CORPUS_MCP_READ_BEARER_TOKEN`;
- `tos-corpus-mcp-read-bearer-token`;
- `mcp:tos-corpus:read`;
- `aoa-loopback-codex:tos-corpus:read`.

This source contour is ready for a filesystem-read-only
`aoa-organ-mcp-read@tos-corpus.service`, but it remains outside the default
bundle until the deployed workspace wrapper and live canary required by
`ABYSS-STACK-D-0077` exist. A provisioned credential is not admission.

## Local Checks

Use the `mcp/services/tos-corpus-mcp/AGENTS.md` route in the repository
[`VALIDATION.md`](../../../VALIDATION.md).
