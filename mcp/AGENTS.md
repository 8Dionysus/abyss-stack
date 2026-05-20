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

## Read before editing

1. Root `AGENTS.md`
2. `DESIGN.md`
3. `BOUNDARIES.md`
4. This card
5. `mcp/services/AGENTS.md` for service packages
6. The package-local `AGENTS.md`, `README.md`, and design docs

## Boundaries

MCP packages may expose resources, tools, prompts, smoke tests, and access
helpers. They may not promote sibling-owned truth by themselves.

For memory work, `mcp/services/aoa-memo-mcp/` exposes `aoa-memo`, `.aoa`, and
local `memo/` routes while keeping durable memory review in `aoa-memo`.

## Validation

For `aoa-memo-mcp` changes, run:

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mcp/services/aoa-memo-mcp/tests -q
```

For release-facing stack changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Closeout

Name the MCP package, exposed resource/tool/prompt changes, owner layer touched,
and whether the change widened runtime exposure or only changed stdio access.
