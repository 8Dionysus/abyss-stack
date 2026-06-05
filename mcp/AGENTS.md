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

For decision-rationale navigation, `mcp/services/aoa-decisions-mcp/` exposes
fresh workspace decision graph packets while keeping rationale authority in
repo-local `docs/decisions/`.

For bounded proof work, `mcp/services/aoa-evals-mcp/` exposes `aoa-evals`
catalog, bundle, comparison, runtime-candidate, and report-skeleton routes
while keeping proof authority in `aoa-evals`.

For host-machine context work, `mcp/services/abyss-machine-mcp/` exposes
`abyss-machine` bridge, evidence, resource, memory, typing, nervous, heartbeat,
and change-ledger read models while keeping host authority in `abyss-machine`.

For session-evidence context work, `mcp/services/aoa-session-memory-mcp/`
exposes `.aoa` search, route traces, atlas maps, session briefs, retrieval
packets, freshness checks, and diagnostics while keeping raw/session authority
in `.aoa`.

## Validation

For `aoa-memo-mcp` changes, run:

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mcp/services/aoa-memo-mcp/tests -q
```

For `aoa-decisions-mcp` changes, run:

```bash
python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py
python -m pytest mcp/services/aoa-decisions-mcp/tests -q
```

For `aoa-evals-mcp` changes, run:

```bash
python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py
python -m pytest mcp/services/aoa-evals-mcp/tests -q
```

For `abyss-machine-mcp` changes, run:

```bash
python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py
python -m pytest mcp/services/abyss-machine-mcp/tests -q
```

For `aoa-session-memory-mcp` changes, run:

```bash
python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
python -m pytest mcp/services/aoa-session-memory-mcp/tests -q
```

For release-facing stack changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Closeout

Name the MCP package, exposed resource/tool/prompt changes, owner layer touched,
and whether the change widened runtime exposure or only changed stdio access.
