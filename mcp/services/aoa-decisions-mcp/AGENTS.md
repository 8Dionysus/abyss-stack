# AGENTS.md

Local route card for `mcp/services/aoa-decisions-mcp/`.

## Purpose

`aoa-decisions-mcp` is the thin MCP access plane for workspace decision
rationale graphs.

It lets agents search decision records, inspect decision neighborhoods, and get
compact decision packets from any working directory while keeping repo-local
`docs/decisions/` records as the source of truth.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, CLI, smoke tests, and service-local docs for
  decision graph access.
- Mandatory lazy freshness over the ignored local graph cache under
  `Logs/decision-graph/latest/`.
- Decision-surface coverage reporting for every fingerprinted
  `docs/decisions/` input.
- The access-plane boundary between source repo decision lanes and agent-facing
  graph packets.

It does not own:

- repo-local decision record meaning;
- generated repo-local decision indexes;
- durable memory, proof, routing, skill, playbook, KAG, stats, or source
  doctrine in sibling repositories;
- hook, timer, or daemon installation.

## Start Here

1. `README.md`
2. `DESIGN.md`
3. `docs/BOUNDARIES.md`
4. `docs/THREAT_MODEL.md`
5. `src/aoa_decisions_mcp/core.py`
6. `src/aoa_decisions_mcp/server.py`
7. `tests/`

## Route Modes

| Need | First route |
|---|---|
| MCP resource, tool, or prompt shape | `src/aoa_decisions_mcp/server.py` |
| freshness and graph packet behavior | `src/aoa_decisions_mcp/core.py` |
| impact, symmetry, or issue packets | `src/aoa_decisions_mcp/core.py` |
| graph builder contract | `scripts/build_workspace_decision_graph.py` |
| repo-local decision meaning | the owning repo's `docs/decisions/` |
| source validation | `scripts/generate_decision_indexes.py --check` and repo-local validators |

## AGENTS Stack Law

- MCP exposes access; it does not promote generated graph packets to source
  truth.
- Every read route must call `ensure_fresh()` before reading graph outputs.
- Refresh may write only the ignored local graph cache under `Logs/`.
- Do not hide unmodeled decision-lane files; add a graph-registry entry or
  report a summary issue.
- Do not install hooks, timers, or daemons from this package.

## Run

For source-local service execution from the `abyss-stack` repo root, run:

```bash
python mcp/services/aoa-decisions-mcp/scripts/aoa_decisions_mcp_server.py
```

If the package is installed, the server entry point is:

```bash
aoa-decisions-mcp-server
```

## Smoke

```bash
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli status
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli summary
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli search "decision graph"
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli packet --query "decision graph"
```

## Verify

```bash
python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py
python -m pytest mcp/services/aoa-decisions-mcp/tests -q
python mcp/services/aoa-decisions-mcp/scripts/release_check.py
```

When parent MCP routing changes, also run:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Report

State which MCP surface changed, whether mandatory freshness behavior changed,
what validation ran, and whether the change widened runtime exposure or only
changed stdio access.
