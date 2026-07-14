# Federated Stats MCP Access Plane

- Decision ID: ABYSS-STACK-D-0078
- Status: accepted
- Date: 2026-07-14
- Owner surface: `mcp/services/aoa-stats-mcp/`

## Index Metadata

- Original date: 2026-07-14
- Surface classes: MCP access plane, federated stats read contract, owner-local stats ports
- Stack lanes: MCP services, validation lane, runtime access plane
- Mechanic parents: none
- Guard families: read-only access plane, packet semantic parity, owner-route confinement, MCP port confinement
- Posture: accepted federated stats access-plane rationale

## Context

`aoa-stats` now owns a shared measurement grammar, a canonical owner inventory,
derived read-model profiles, and a transport-neutral packet read contract.
Every active owner repository has its own root `stats/` port or an explicit
stronger-owner route. Agents need one bounded access path across those surfaces.

The previous MCP implementation lived inside `aoa-stats`, mixed source reads
with runtime transport, and exposed an intake source registry as though it were
the federated owner map. Runnable MCP services and their transport lifecycle
belong to `abyss-stack`, while statistical and owner-local meaning do not.

## Options considered

- Keep direct repository reads as the only access route.
- Copy the central schemas and packet semantics into a stack service.
- Keep the stable public contracts in `aoa-stats` and add a stack-owned
  read-only adapter that consumes them without reimplementing their meaning.

## Decision

Choose the third option.

Add `mcp/services/aoa-stats-mcp/` as the runnable access plane. Preserve the
proven `stats_catalog`, `stats_surface_read`, and `stats_boundary_rules` tool
names. Add `stats_owner_port_read` for canonical inventory and owner-local port
inspection, and `stats_packet_check` for the public packet-reader boundary.

The service confines filesystem reads to the configured `aoa-stats` root,
catalog-listed derived surfaces, and inventory-declared owner ports. Source
routes outside the workspace require explicit mapping. Missing or unresolved
materialization remains visible instead of becoming an inferred success.

Packet checking invokes `aoa-stats/scripts/read_measurement_packet.py` through
JSON standard input and returns its result unchanged. The service does not
recompute compatibility, semantic identity, evidence identity, or authority.

The initial MCP surface is closed-world and read-only. No resource or prompt is
added without a demonstrated consumer. The old `stats_source_registry` tool is
not migrated because the receipt-source registry is an intake implementation
surface, not the owner federation inventory.

## Rationale

This split gives agents one access plane without making runtime convenience a
new statistical authority. The public packet reader is a narrow subprocess
port: `aoa-stats` retains semantic law, while the stack adapter owns process,
filesystem, error, and transport concerns. Explicit inventory routes prevent a
workspace crawl from silently inventing owners or accepting arbitrary paths.

Keeping the tool set consumer-backed avoids rebuilding the old repo-local MCP
as a larger framework. Closed-world read-only annotations let clients preserve
the intended non-mutating authority boundary.

## Consequences

- Positive: direct and MCP packet reads share one semantic and evidence
  identity result.
- Positive: agents can inspect substantially different local ports without
  copying their evidence or domain meaning into `aoa-stats` or `abyss-stack`.
- Positive: committed projections, live materializations, unresolved source
  routes, missing ports, and freshness-unattested reads stay distinguishable.
- Tradeoff: non-workspace source roots need explicit runtime configuration.
- Tradeoff: catalog and owner availability remain weaker than evidence truth or
  freshness.
- Follow-up: land the workspace wrapper and registration through their owner,
  canary the single active service, then remove the repo-local implementation
  and obsolete registration from `aoa-stats`.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-stats-mcp/AGENTS.md`
- `mcp/services/aoa-stats-mcp/DESIGN.md`
- `mcp/services/aoa-stats-mcp/README.md`
- `mcp/services/aoa-stats-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-stats-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-stats-mcp/src/aoa_stats_mcp/core.py`
- `mcp/services/aoa-stats-mcp/src/aoa_stats_mcp/server.py`
- `mcp/services/aoa-stats-mcp/src/aoa_stats_mcp/cli.py`
- `mcp/services/aoa-stats-mcp/scripts/validate_stats_mcp.py`
- `mcp/services/aoa-stats-mcp/tests/test_stats_mcp.py`
- `docs/validation/validation_lanes.json`
- `docs/validation/script_inventory.json`
- `docs/validation/validator_inventory.json`
- `docs/testing/test_inventory.json`
- `scripts/validators/source_structure.py`
- `scripts/validate_nested_agents.py`
- `tests/test_runtime_lifecycle_user_unit.py`
- `aoa-stats:stats/federation/owner-inventory.json`
- `aoa-stats:stats/measurement-contract/packet-read-request.schema.json`
- `aoa-stats:stats/measurement-contract/packet-read-result.schema.json`
- `aoa-stats:scripts/read_measurement_packet.py`
- `aoa-stats:docs/decisions/AOST-D-0012-federated-measurement-ownership-and-thin-access.md`

## Follow-up route

Use the Codex-plane registration owner after this package is merged and
projected. Prove direct-versus-MCP parity and one active registration before
the `aoa-stats` owner removes its repo-local MCP implementation.
