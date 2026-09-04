# AGENTS.md

Local route card for `mcp/services/aoa-session-memory-mcp/`.

## Purpose

`aoa-session-memory-mcp` is the thin MCP access plane for `.aoa` session
evidence, route maps, retrieval packets, freshness checks, and diagnostic
readiness.

It lets agents debug durable agent-process anchors such as skills, MCPs, hooks,
tools, paths, goals, failures, decisions, writeback pressure, and recurring
patterns without turning MCP into archive authority.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, CLI, smoke tests, and service-local docs for
  session-evidence access.
- The local transport boundary between `abyss-stack` and `.aoa`: portable
  stdio by default and optional authenticated loopback shared HTTP under
  `ABYSS-STACK-D-0077`.
- Compact route/evidence packets that preserve refs into `.aoa`.

It does not own:

- raw transcript evidence, generated indexes, maps, search schemas, or
  diagnostics, owned by `.aoa`;
- durable reviewed memory truth, owned by `aoa-memo`;
- source truth in sibling repositories;
- maintenance, reindex, repair, distillation, naming, relabel, export, or
  promotion authority.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Route Modes

| Need | First route |
|---|---|
| MCP resource, tool, or prompt shape | `src/aoa_session_memory_mcp/server.py` |
| route/search/readiness command wrapping | `src/aoa_session_memory_mcp/core.py` |
| `.aoa` archive semantics | `.aoa/AGENTS.md`, `.aoa/DESIGN.md`, `.aoa/DESIGN.AGENTS.md` |
| route maps or atlas axes | `.aoa/maps/README.md` and generated `maps/by-*/index.json` |
| session brief shape | `.aoa` session manifest and index |
| stack package rationale | `docs/decisions/ABYSS-STACK-D-0037-aoa-session-memory-mcp-access-plane.md` |

## AGENTS Stack Law

- MCP exposes access; it does not promote session evidence to truth.
- Return `session_id`, `segment_ref`, `raw_ref`, route signals, and freshness
  whenever possible.
- Search, atlas, and diagnostics are route companions. Raw transcript and
  segment indexes remain stronger evidence.
- Maintenance remains outside MCP and requires explicit operator intent.
- Keep the HTTP read contour owner-specific:
  `AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN`,
  `aoa-session-memory-mcp-read-bearer-token`,
  `mcp:aoa-session-memory:read`, and
  `aoa-loopback-codex:aoa-session-memory:read`.
- Open generated SQLite fast paths with `mode=ro` and `query_only`; the
  filesystem-read-only owner unit must remain executable without writable
  projection paths.

## Run

For source-local service execution from the `abyss-stack` repo root, use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

If the package is installed, the server entry point is:


Codex may either start the portable stdio server once per Codex process or
attach to the source-owned authenticated loopback shared HTTP owner. Existing
tool implementations auto-reload `core.py` when its source hash changes, but
tool-surface, schema, server-wrapper, or Python import-path changes still
require restarting the configured owner before treating `tool_search` /
`mcp__aoa_session_memory.*` output as current. Killing an attached stdio server
closes that transport; restarting a shared HTTP owner does not itself prove
that an already-running Codex client reloaded changed tool schemas.

## Verify


When parent MCP routing changes, also use the on-demand validation route in `VALIDATION.md`.


## Report

State which MCP surface changed, which `.aoa` route/search/readiness surface it
wraps, what validation ran, and whether the change affected portable stdio,
loopback shared HTTP, or any wider runtime exposure.
