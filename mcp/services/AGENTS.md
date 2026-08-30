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

The runnable package map lives in `mcp/services/README.md`. For one package,
run the exact commands in its service-local `AGENTS.md`; do not inherit or run
unrelated package matrices. For a district-wide change, run:

```bash
python scripts/ci_gate.py --mode mcp-services
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
