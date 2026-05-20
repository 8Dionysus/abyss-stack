# AGENTS.md

Local route card for `mcp/services/aoa-memo-mcp/`.

## Purpose

`aoa-memo-mcp` is the thin MCP access plane for OS Abyss memory.
It lets agents read memory briefs, inspect local memo ports, create reviewed
memory candidates, validate candidates, and route session rehydration without
turning MCP into memory authority.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, and smoke tests for memory access.
- The access-plane boundary between `aoa-memo`, `.aoa`, repo-local `memo/`
  ports, and host-local memory evidence.
- Candidate creation and validation helpers that remain subordinate to
  `aoa-memo` contracts.

It does not own:

- durable reviewed memory truth, owned by `aoa-memo`;
- raw session evidence, owned by `.aoa`;
- runtime or host truth, owned by `abyss-stack` and `abyss-machine`;
- repo-local meaning in the pilot repositories.

## Start Here

1. `README.md`
2. `DESIGN.md`
3. `docs/BOUNDARIES.md`
4. `docs/THREAT_MODEL.md`
5. `src/aoa_memo_mcp/core.py`
6. `src/aoa_memo_mcp/server.py`
7. `tests/`

## Route Modes

| Need | First route |
|---|---|
| MCP resource, tool, or prompt shape | `src/aoa_memo_mcp/server.py` |
| memory route semantics | `DESIGN.md` and `docs/BOUNDARIES.md` |
| candidate validation | `src/aoa_memo_mcp/core.py` |
| pilot local port posture | target repo `memo/AGENTS.md` |
| session archive access | `.aoa/AGENTS.md` and `.aoa/DESIGN.md` |

## AGENTS Stack Law

- Start with this card, then follow the nearest nested `AGENTS.md`.
- MCP exposes access; it does not promote memory to truth.
- Local ports store candidates and receipts; `aoa-memo` decides durable memory.
- `.aoa` raw/session material remains evidence and is never flattened into MCP
  summaries as authority.

## Verify

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mcp/services/aoa-memo-mcp/tests -q
python mcp/services/aoa-memo-mcp/scripts/release_check.py
```

## Report

State which MCP surface changed, which owner boundary was touched, which pilot
port was involved, what validation ran, and whether any durable memory write
was attempted.
