# AGENTS.md

## Applies to

This card applies to `mcp/services/aoa-kag-mcp/` and every nested path until a
nearer card narrows the lane.

## Role

`aoa-kag-mcp` is the thin read-only MCP access plane over canonical repo-local
KAG records and stack-owned runtime projections.

Its public behavior is the compact `discover`, `search`, `read`, `traverse`,
and `explain` application protocol. Results preserve owner identity, source
anchors, provenance, freshness, access, projection state, and evidence routes.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.
## Boundaries

Repo-local `kag/` homes own canonical repository records. `aoa-kag` owns the
common schemas, qualified identity, retrieval semantics, federation,
provenance, freshness, generated provider map, and source-return handoff.
`kag-seam` owns runtime adapters and mutable projection state. This package
owns MCP mapping, resources, transports, CLI, service validation, and focused
contract tests.

## Validation

For this service,use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For service-route changes, alsouse the on-demand validation route in `VALIDATION.md`.


## Closeout

Report the five-tool contract, resources, application route, owner layer
touched, degradation behavior, and whether portable stdio or loopback HTTP
changed.
