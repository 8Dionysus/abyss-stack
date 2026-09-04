# AGENTS.md

## Applies to

This card applies to `mcp/services/aoa-stats-mcp/` and every nested path until
a nearer card narrows the lane.

## Role

`aoa-stats-mcp` is the thin read-only MCP access plane for the shared
`aoa-stats` contracts, derived catalog, owner inventory, and owner-local root
`stats/` ports.

It preserves the source owners' measurement meaning and delegates packet
compatibility to the public `aoa-stats` read contract.

Use `stats_owner_port_read` for canonical inventory and owner-local definition
inspection; its output is discovery evidence, not an attestation of owner
truth or freshness.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Boundaries

- `aoa-stats` owns statistical grammar, compatibility, semantic identity,
  derived profiles, and the canonical owner inventory.
- Each root `stats/` port owns its questions, measures, populations, evidence
  handoffs, privacy, and freshness posture.
- This package owns discovery, bounded filesystem reads, subprocess transport,
  MCP tools, and local transport lifecycle only.
- Do not accept arbitrary filesystem reads, raw session content, writes,
  refresh operations, eval verdicts, routing decisions, or runtime mutation.
- Do not reimplement packet semantics in this package.

## Validation

After manual positive and negative journeys establish the behavior, use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

## Closeout

Report the tools changed, the owner contracts consumed, direct-versus-MCP
semantic identity evidence, and whether portable stdio, authenticated loopback
HTTP, registration, or any wider runtime exposure changed.
