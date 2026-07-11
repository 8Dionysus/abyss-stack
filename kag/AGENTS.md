# AGENTS.md

## Applies to

This card applies to `abyss-stack/kag/` and every nested path until a nearer
card narrows the lane.

## Role

`kag/` is the repository-local KAG provider home for `abyss-stack`. It exposes
source-linked records and generated repository indexes over the runtime source
home, mechanics, and MCP access plane.

## Read before editing

Read the root `AGENTS.md`, this card, `kag/README.md`, `kag/manifest.json`,
`README.md`, `DESIGN.md`, `mechanics/README.md`, and `mcp/README.md` before
changing provider records.

## Boundaries

Runtime source meaning belongs to `abyss-stack`. Shared KAG schema, registry,
composition, and provider validation belong to `aoa-kag`. Live services,
secrets, logs, models, caches, databases, and generated runtime indexes stay in
the deployed runtime roots.

## Validation

Use the owner validator named in `manifest.json`, then validate this provider
through the `aoa-kag` local subtree validator.

## Closeout

Report provider records changed, source-return route changed, owner validation,
`aoa-kag` validation, and the affected runtime or MCP consumer route.
