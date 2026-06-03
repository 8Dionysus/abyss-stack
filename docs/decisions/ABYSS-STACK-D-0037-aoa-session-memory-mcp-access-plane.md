# AoA Session Memory MCP Access Plane

- Decision ID: ABYSS-STACK-D-0037
- Status: accepted
- Date: 2026-05-26
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-26
- Surface classes: MCP access plane, federation/read-model
- Stack lanes: MCP services, federation seams
- Mechanic parents: federation-seams
- Guard families: read-only access plane, MCP port confinement
- Posture: accepted session-memory access-plane rationale

## Context

`.aoa` is the session evidence and route-intelligence kernel for OS Abyss. It
preserves raw Codex transcripts, compaction boundaries, segment indexes, route
signals, atlas maps, search indexes, diagnostics, retrieval packets, naming
queues, and later reviewed distillation routes.

Agents need a compact way to debug stable operational anchors across sessions:
skills, MCPs, hooks, tools, paths, repos, commands, configs, goals, decisions,
failures, writeback pressure, freshness drift, and recurring process patterns.

MCP services belong in `abyss-stack`, but session evidence authority belongs
in `.aoa`.

## Options considered

1. Keep session evidence access as direct repository and CLI reads only.
2. Extend `aoa-memo-mcp` to answer all session-evidence and route-map queries.
3. Add a distinct `aoa-session-memory-mcp` service in `abyss-stack` as a
   read-only access-plane adapter over `.aoa`.

## Decision

Choose option 3.

Add `mcp/services/aoa-session-memory-mcp/` as the stack-owned runnable MCP
package for the stable Codex server name `aoa_session_memory`.

The service exposes read-only resources, tools, and prompts for:

- search provider status, atlas readiness, and route diagnostics;
- session search with route filters and evidence refs;
- anchor tracing across entity, skill, MCP, hook, tool, path, git/GitHub, and
  external route coordinates;
- generated atlas axis/key lookup;
- compact session briefs;
- retrieval packets;
- candidate evidence packets for writeback/debug/review;
- freshness checks;
- pattern scans;
- plan-only maintenance guidance.

The service wraps fixed `.aoa` read commands and reads fixed generated JSON
surfaces. It does not write, reindex, repair, relabel, distill, name, export,
install, promote, accept evidence, or land durable memory.

## Rationale

This preserves the owner split. `abyss-stack` owns the runtime adapter and MCP
service shape. `.aoa` owns session evidence, generated indexes, route-signal
classification, search, atlas, diagnostics, and archival semantics.

It also keeps `aoa-memo-mcp` focused on durable memory and writeback/candidate
routes. Session evidence can feed memory review, but it is not the same organ.

## Consequences

- Agents can use `aoa_session_memory` to find and inspect session evidence
  without context flooding.
- Stable agent-process anchors are treated as route coordinates, not as a
  hardcoded list of special entity types.
- Every response must preserve evidence refs and authority boundaries.
- Maintenance remains outside MCP and requires explicit operator intent.
- Future non-stdio exposure, write tools, reindex/repair/distillation routes,
  bulk raw transcript resources, durable memory landing, or host accelerator
  authority require a new decision.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-session-memory-mcp/AGENTS.md`
- `mcp/services/aoa-session-memory-mcp/DESIGN.md`
- `mcp/services/aoa-session-memory-mcp/README.md`
- `mcp/services/aoa-session-memory-mcp/src/aoa_session_memory_mcp/core.py`
- `mcp/services/aoa-session-memory-mcp/src/aoa_session_memory_mcp/server.py`
- `.aoa:AGENTS.md`
- `.aoa:DESIGN.md`
- `.aoa:DESIGN.AGENTS.md`

## Follow-up route

Run:

```bash
python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
python -m pytest mcp/services/aoa-session-memory-mcp/tests -q
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

Register the shared Codex-plane server name `aoa_session_memory` through the
Codex-plane owner surfaces before claiming it is available to new Codex
sessions.
