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

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Route Modes

| Need | First route |
| --- | --- |
| MCP resource, tool, or prompt shape | `src/abyss_machine_mcp/server.py` |
| compact machine brief | `src/abyss_machine_mcp/core.py` `machine_brief()` |
| owner and evidence map | `evidence_map()` and `authority_boundary()` |
| existing machine RAG trace | `surface("rag-latest")`; trace creation stays on the owner CLI effect route |
| safe launch/mutation posture | `machine_route()` and `abyss-machine changes preflight` refs |
| live host truth | `abyss-machine` source contracts and validators |
| durable host rationale | `/etc/abyss-machine/decisions/` |
| stack package rationale | `docs/decisions/ABYSS-STACK-D-0036-abyss-machine-mcp-access-plane.md` |

## AGENTS Stack Law

- MCP exposes access; it does not become host authority.
- Use only allowlisted `abyss-machine ... --json` read-model commands.
- Classify the actual owner CLI behavior. A status, trace, recall, coverage, or
  validator that writes generated/latest state is not a read route.
- Do not add arbitrary shell, privileged commands, service restarts, process
  mutation, source mutation, or private raw capture reads.
- Treat generated/latest JSON as evidence and route accelerators; source
  contracts under `/etc/abyss-machine` remain stronger.
- Keep stdio as the portable default. The optional shared Streamable HTTP
  owner must stay authenticated and loopback-only under
  `ABYSS-STACK-D-0077`; any wider or remote exposure requires a later
  decision.

## Run

For source-local service execution from the `abyss-stack` repo root, use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

If the package is installed, the server entry point is:


## Verify


When parent MCP routing changes, also use the on-demand validation route in `VALIDATION.md`.


## Report

State which MCP surface changed, which `abyss-machine` read-model commands it
exposes, what validation ran, and whether runtime exposure, mutation authority,
private capture access, privileged commands, or source ownership changed.
