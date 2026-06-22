# AGENTS.md

## Applies to

This card applies to `mcp/services/` and every MCP service package below it.

## Role

`mcp/services/` is the service-package district for stack-owned Model Context
Protocol servers. It keeps runnable MCP access planes below one route instead
of leaving service packages directly in the root-adjacent `mcp/` district.

## Read before editing

1. Root `AGENTS.md`
2. `mcp/AGENTS.md`
3. This card
4. The service-local `AGENTS.md`, README, design notes, source, and tests

## Boundaries

Service packages may own MCP server code, service-local docs, tests, prompts,
resources, tools, and smoke helpers. Source authority stays with the owner layer
named by the service-local route card.

## Validation

For `aoa-memo-mcp`, run:

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mcp/services/aoa-memo-mcp/tests -q
```

For `aoa-decisions-mcp`, run:

```bash
python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py
python -m pytest mcp/services/aoa-decisions-mcp/tests -q
```

For `aoa-evals-mcp`, run:

```bash
python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py
python -m pytest mcp/services/aoa-evals-mcp/tests -q
```

For `abyss-machine-mcp`, run:

```bash
python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py
python -m pytest mcp/services/abyss-machine-mcp/tests -q
```

For `aoa-session-memory-mcp`, run:

```bash
python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
python -m pytest mcp/services/aoa-session-memory-mcp/tests -q
```

For `tos-corpus-mcp`, run:

```bash
python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py
python -m pytest mcp/services/tos-corpus-mcp/tests -q
```

For `aoa-4pda-connector-mcp`, run:

```bash
python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q
```

When a service path, local route card, or root district route changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Closeout

Name the service package, the MCP surface that changed, and whether the change
only moved access-plane topology or also changed resources, tools, prompts, or
runtime exposure.
