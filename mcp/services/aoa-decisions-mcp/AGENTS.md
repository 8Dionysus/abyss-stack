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
- An effect-isolated refresh contour for the ignored local graph cache under
  `Logs/decision-graph/latest/`.
- A read contour that checks cache parity but cannot create, lock, or refresh
  graph outputs.
- Honest local source-posture reporting without remote fetch or checkout
  mutation.
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

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

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
- Every read route must call `require_fresh()` before reading graph outputs.
- `AOA_DECISIONS_MCP_CONTOUR=read` is the default and cannot write cache
  output; `internal_effect` exposes only cache posture and explicit refresh.
- Keep `cache_status`, source posture, and remote freshness as distinct claims.
- The internal-effect refresh contour may write only the ignored local graph
  cache under `Logs/`.
- Do not hide unmodeled decision-lane files; add a graph-registry entry or
  report a summary issue.
- Do not install hooks, timers, or daemons from this package.
- `AOA_DECISIONS_MCP_CAPABILITY_PROFILE=decision-retrieval` selects the exact
  organ read profile. It must remain bound to `organ-access.v1.json` and is
  invalid for `internal_effect`.

## Run

For source-local service execution from the `abyss-stack` repo root, use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

This starts the read contour. An internal-effect server must be a separate
process and credential:


The owner-local CLI remains the non-MCP cache preparation route:


If the package is installed, the server entry point is:


## Verify


When parent MCP routing changes, also use the on-demand validation route in `VALIDATION.md`.


## Report

State which MCP contour changed, whether cache parity behavior changed, what
validation ran, and whether the change affected portable stdio, loopback HTTP,
or any wider runtime exposure.
