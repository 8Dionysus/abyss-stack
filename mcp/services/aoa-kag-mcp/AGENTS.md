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

## Read before editing

Read root `AGENTS.md`, `mcp/AGENTS.md`, `mcp/services/AGENTS.md`, this card,
`README.md`, `DESIGN.md`, `docs/BOUNDARIES.md`, `docs/THREAT_MODEL.md`, source,
tests, and `aoa-kag/kag/LOCAL_SUBTREE_PROTOCOL.md` before changing behavior.

## Boundaries

Repo-local `kag/` homes own canonical repository records. `aoa-kag` owns the
common schemas, qualified identity, retrieval semantics, federation,
provenance, freshness, generated provider map, and source-return handoff.
`kag-seam` owns runtime adapters and mutable projection state. This package
owns MCP mapping, resources, transports, CLI, service validation, and focused
contract tests.

## Validation

For this service, run:

```bash
python mcp/services/aoa-kag-mcp/scripts/validate_kag_mcp.py
python -m pytest mcp/services/aoa-kag-mcp/tests -q
```

For service-route changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Closeout

Report the five-tool contract, resources, application route, owner layer
touched, degradation behavior, and whether portable stdio or loopback HTTP
changed.
