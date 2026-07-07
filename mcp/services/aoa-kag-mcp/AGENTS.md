# AGENTS.md

## Applies to

This card applies to `mcp/services/aoa-kag-mcp/` and every nested path until a
nearer card narrows the lane.

## Role

`aoa-kag-mcp` is a thin read-only MCP access plane over the `aoa-kag` provider
map and repo-local `kag/` provider packets.

It helps agents inspect provider status, source-return routes, freshness
handles, generation routes, source-index handles, repo-local coverage,
registry slices, and bounded provider records without turning the MCP service
into KAG source authority.

## Read before editing

Read root `AGENTS.md`, `mcp/AGENTS.md`, `mcp/services/AGENTS.md`, this card,
`README.md`, `DESIGN.md`, `docs/BOUNDARIES.md`, `docs/THREAT_MODEL.md`, source,
tests, and `aoa-kag/kag/LOCAL_SUBTREE_PROTOCOL.md` before changing behavior.

## Boundaries

`aoa-kag` owns schema, readiness, generated provider map, provider validation,
and KAG composition meaning. Repo-local `kag/` homes own their source-return
handles. This package owns only MCP resource, tool, prompt, CLI, validator, and
test shape.

Runtime graph, vector, embedding, cache, and serving state stay outside this
package unless a later source-owned contract adds that route.

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

Report resources, tools, prompts, provider-map shape, owner layer touched, and
whether the change only widened stdio access or also changed runtime exposure.
