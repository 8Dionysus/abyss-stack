# AGENTS.md

Local route card for `mcp/services/abyss-machine-mcp/`.

## Purpose

`abyss-machine-mcp` is the thin MCP access plane for the local host-machine
read model. It lets agents obtain compact, typed, owner-aware machine context
without turning MCP into host authority or a command shell.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, CLI, smoke tests, and package-local docs for
  machine context access.
- The adapter boundary between `abyss-machine` bridge/read-model commands and
  Codex/OS Abyss agents.
- Compact owner, evidence, constraint, and safe-next-route summaries derived
  from existing `abyss-machine` contracts.

It does not own:

- host facts, policies, generated indexes, change ledgers, or hardware
  evidence, owned by `abyss-machine`;
- durable reviewed memory, owned by `aoa-memo`;
- proof/verdict authority, owned by `aoa-evals`;
- stack runtime promotion decisions, owned by `abyss-stack`;
- private raw capture interpretation, operator intent, or arbitrary shell
  execution.

## Start Here

1. `README.md`
2. `DESIGN.md`
3. `docs/BOUNDARIES.md`
4. `docs/THREAT_MODEL.md`
5. `src/abyss_machine_mcp/core.py`
6. `src/abyss_machine_mcp/server.py`
7. `tests/`

## Route Modes

| Need | First route |
| --- | --- |
| MCP resource, tool, or prompt shape | `src/abyss_machine_mcp/server.py` |
| compact machine brief | `src/abyss_machine_mcp/core.py` `machine_brief()` |
| owner and evidence map | `evidence_map()` and `authority_boundary()` |
| machine RAG trace | `machine_rag_trace()` and `abyss-machine rag trace --query TEXT --json` |
| safe launch/mutation posture | `machine_route()` and `abyss-machine changes preflight` refs |
| live host truth | `abyss-machine` source contracts and validators |
| durable host rationale | `/etc/abyss-machine/decisions/` |
| stack package rationale | `docs/decisions/2026-05-25-abyss-machine-mcp-access-plane.md` |

## AGENTS Stack Law

- MCP exposes access; it does not become host authority.
- Use only allowlisted `abyss-machine ... --json` read-model commands.
- Do not add arbitrary shell, privileged commands, service restarts, process
  mutation, source mutation, or private raw capture reads.
- Treat generated/latest JSON as evidence and route accelerators; source
  contracts under `/etc/abyss-machine` remain stronger.
- Keep the server stdio-only unless a later decision widens exposure.

## Run

For source-local service execution from the `abyss-stack` repo root, run:

```bash
python mcp/services/abyss-machine-mcp/scripts/abyss_machine_mcp_server.py
```

If the package is installed, the server entry point is:

```bash
abyss-machine-mcp-server
```

## Smoke

```bash
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli brief
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli evidence-map
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli maps --axis by-freshness --query semantic --limit 8
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli context-packet --axis by-eval-packet --reader-profile proof-context --limit 4
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli rag-trace --query "machine RAG trace loop" --limit 4 --evidence-limit 6
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli surface memory-pressure
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli route --intent "start bounded local AI work" --class heavy --kind ai
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli read-resource abyss-machine://brief
```

## Verify

```bash
python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py
python -m pytest mcp/services/abyss-machine-mcp/tests -q
python mcp/services/abyss-machine-mcp/scripts/release_check.py
```

When parent MCP routing changes, also run:

```bash
python scripts/validate_decision_records.py
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Report

State which MCP surface changed, which `abyss-machine` read-model commands it
exposes, what validation ran, and whether runtime exposure, mutation authority,
private capture access, privileged commands, or source ownership changed.
