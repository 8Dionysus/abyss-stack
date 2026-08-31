# AGENTS.md

## Applies to

This card applies to `mcp/` and all stack-owned MCP access-plane packages below
it.

## Role

`mcp/` holds Model Context Protocol servers that expose live or derived
runtime-adjacent context without turning prompts into flattened archives.

The district belongs in `abyss-stack` because MCP servers are runtime access
planes and adapters. The data and meaning they expose still belong to their
owner layers.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Boundaries

MCP packages may expose resources, tools, prompts, smoke tests, and access
helpers. They may not promote sibling-owned truth by themselves.

For MCP protocol migration, `mcp/protocol-lab/` pins the exact stable and next
pairs, retains the stable registration, and blocks migration until pair-level
conformance, read canary, and rollback receipts exist. It is a compatibility
gate, not a server, and it never admits effectful migration.

The runnable package map and human-facing role summaries live in
`mcp/services/README.md`. Each service-local `AGENTS.md` owns its exact owner
split, stop-lines, runtime-exposure posture, and executable checks. Do not copy
that package catalog or its command matrix into this inherited district card.

## Validation

For protocol compatibility changes, use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For one service package, run the exact `Run`, `Smoke`, and `Verify` route in
its nearest `AGENTS.md`. For a change spanning the service district, use the on-demand validation route in `VALIDATION.md`.


For release-facing stack changes, also use the on-demand validation route in `VALIDATION.md`.


## Closeout

Name the MCP package, exposed resource/tool/prompt changes, owner layer touched,
and whether the change widened runtime exposure or only changed stdio access.
