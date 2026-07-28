# Design

## Shape

`aoa-stats-mcp` is a ports-and-adapters boundary around public stats reads.

The reusable center exposes five purpose-shaped operations: catalog read,
surface read, compact boundary read, owner-port read, and packet compatibility
check. Filesystem discovery and subprocess invocation remain adapters.

## Source relationships

`aoa-stats` supplies the canonical owner inventory, source-home manifest,
derived catalog, measurement schemas, and the public packet-reader command.
Owner repositories supply their root `stats/port.manifest.json` and referenced
packets or evidence. This package does not copy either source layer.

The packet adapter sends JSON objects to the public reader over standard input.
It accepts no packet path and returns the owner-produced result without
recomputing semantic or evidence identity.

## Discovery

Workspace routes are resolved beneath the configured OS Abyss workspace root.
Non-workspace source routes require an explicit source-root mapping. An
unresolved or missing port stays visible as such; runtime presence never
silently becomes source truth.

Catalog and surface reads are confined to catalog-listed paths beneath the
configured `aoa-stats` root. Committed projections are identified as
reference-only. A live materialization remains freshness-unattested unless its
owner payload says more.

## Runtime

The package supports portable stdio and an owner-specific authenticated
loopback HTTP read contour. Transport does not change tool semantics or source
authority. The `aoa-stats` read token, credential name, scope, and client
identity are not accepted by sibling owners.
