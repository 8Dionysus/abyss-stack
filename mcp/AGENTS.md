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
5. `mcp/protocol-lab/AGENTS.md` for protocol compatibility work
6. `mcp/services/AGENTS.md` for service packages
7. The package-local `AGENTS.md`, `README.md`, and design docs

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

For protocol compatibility changes, run:

```bash
python mcp/protocol-lab/scripts/build_protocol_lab_status.py --check
python mcp/protocol-lab/scripts/validate_protocol_lab.py
python -m pytest mcp/protocol-lab/tests -q
```

For one service package, run the exact `Run`, `Smoke`, and `Verify` route in
its nearest `AGENTS.md`. For a change spanning the service district, run:

```bash
python scripts/ci_gate.py --mode mcp-services
```

For release-facing stack changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Closeout

Name the MCP package, exposed resource/tool/prompt changes, owner layer touched,
and whether the change widened runtime exposure or only changed stdio access.
