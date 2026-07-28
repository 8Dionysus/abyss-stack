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

## Start Here

1. `README.md`
2. `DESIGN.md`
3. `docs/BOUNDARIES.md`
4. `docs/THREAT_MODEL.md`
5. `.aoa/AGENTS.md`, `.aoa/DESIGN.md`, and `.aoa/DESIGN.AGENTS.md` when route
   semantics may move
6. `src/aoa_session_memory_mcp/core.py`
7. `src/aoa_session_memory_mcp/server.py`
8. `tests/`

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

For source-local service execution from the `abyss-stack` repo root, run:

```bash
python mcp/services/aoa-session-memory-mcp/scripts/aoa_session_memory_mcp_server.py
```

If the package is installed, the server entry point is:

```bash
aoa-session-memory-mcp-server
```

Codex may either start the portable stdio server once per Codex process or
attach to the source-owned authenticated loopback shared HTTP owner. Existing
tool implementations auto-reload `core.py` when its source hash changes, but
tool-surface, schema, server-wrapper, or Python import-path changes still
require restarting the configured owner before treating `tool_search` /
`mcp__aoa_session_memory.*` output as current. Killing an attached stdio server
closes that transport; restarting a shared HTTP owner does not itself prove
that an already-running Codex client reloaded changed tool schemas.

## Smoke

```bash
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli status
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli transport-preflight
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-responses --session latest --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-closeouts --session latest --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-progress-updates --session latest --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-reasoning-windows --session latest --limit 2
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli task-episodes latest --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli goal-lifecycles latest --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli answer-neighborhood --session latest --limit 2
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli trace aoa-session-memory-mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-chain aoa-session-memory-mcp --kind mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli entity-dossier aoa-session-memory-mcp --kind mcp --usage-limit 2 --neighborhood-limit 1 --graph-limit 6 --graph-edge-limit 6
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-audit aoa-session-memory-mcp --kind mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-neighborhood view_image --kind tool --limit 2
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-scenario-audit --seed smoke --sample-size 4
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli live-scenario-audit --profile entity_registry_lookup --seed smoke --sample-size 5 --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli live-scenario-corpus-list
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli live-scenario-corpus-check --case-limit 1
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli search aoa-session-memory --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli search --filter route_signal=tool:view_image --filter doc_type=event --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli entity-inventory --layer skill --limit 10
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli entity-inventory --layer git --limit 10
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli hook-receipts --event-name UserPromptSubmit --only-errors --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli projection-status
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli route-rollup-query exec_command --layer tool --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli direct-event-rollup-query --usage-role result --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli route by-mcp aoa-session-memory-mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli brief latest
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli evidence-packet --intent "debug aoa-session-memory-mcp" --anchor aoa-session-memory-mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli freshness-check raw:line:1 --session latest
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-neighborhood aoa-session-memory-mcp --kind mcp --limit 20
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-bridge aoa-session-memory-mcp exec_command --source-kind mcp --target-kind tool --limit 4
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-cooccurrence aoa-session-memory-mcp --kind mcp_service --limit 6
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graphrag-packet aoa-session-memory-mcp --anchor aoa-session-memory-mcp --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-quality-audit --limit 4
```

## Verify

```bash
python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
python -m pytest mcp/services/aoa-session-memory-mcp/tests -q
python mcp/services/aoa-session-memory-mcp/scripts/release_check.py
```

When parent MCP routing changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Report

State which MCP surface changed, which `.aoa` route/search/readiness surface it
wraps, what validation ran, and whether the change affected portable stdio,
loopback shared HTTP, or any wider runtime exposure.
