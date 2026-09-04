# AGENTS.md

Local route card for `mcp/services/aoa-memo-mcp/`.

## Purpose

`aoa-memo-mcp` is the thin MCP access plane for OS Abyss memory.
Its read contour lets agents read memory briefs, inspect local memo ports,
validate candidates, and route session rehydration. Its separately
authenticated candidate contour creates only allowlisted local candidates,
indexes, exports, and forwarding receipts. Neither contour turns MCP into
memory authority.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, and smoke tests for memory access.
- The access-plane boundary between `aoa-memo`, `.aoa`, repo-local `memo/`
  ports, and host-local memory evidence.
- Candidate, local port index, reviewed-intake export, and forwarding receipt
  helpers that remain subordinate to `aoa-memo` contracts.
- Pending-export and landing-plan helpers that expose readiness and dry-run
  evidence without landing durable memory.

It does not own:

- durable reviewed memory truth, owned by `aoa-memo`;
- raw session evidence, owned by `.aoa`;
- runtime or host truth, owned by `abyss-stack` and `abyss-machine`;
- repo-local meaning in the pilot repositories.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Route Modes

| Need | First route |
|---|---|
| MCP resource, tool, or prompt shape | `src/aoa_memo_mcp/server.py` |
| memory route semantics | `DESIGN.md` and `docs/BOUNDARIES.md` |
| candidate validation | `src/aoa_memo_mcp/core.py` plus `aoa-memo/schemas/memory-ports/` |
| local port index or reviewed-intake packet | `src/aoa_memo_mcp/core.py`, `aoa-memo` schemas, and target `memo/PORT.yaml` |
| pending exports or landing plan | `src/aoa_memo_mcp/core.py`, origin `memo/exports/`, and `aoa-memo/scripts/memory/land_reviewed_memo_intake.py` |
| pilot local port posture | target repo `memo/AGENTS.md` |
| session archive access | `.aoa/AGENTS.md` and `.aoa/DESIGN.md` |

## AGENTS Stack Law

- Start with this card, then follow the nearest nested `AGENTS.md`.
- MCP exposes access; it does not promote memory to truth.
- Local ports store candidates, receipts, exports, and generated indexes;
  `aoa-memo` decides durable memory.
- `.aoa` raw/session material remains evidence and is never flattened into MCP
  summaries as authority.

## Run

In the shared AoA Codex plane this service is registered as `aoa_memo` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. Use the workspace
launcher from the shared root when testing the registered route; use [VALIDATION.md](../../../VALIDATION.md).

For source-local service execution from the `abyss-stack` repo root, use the on-demand validation route in `VALIDATION.md`.


The first command defaults to the read contour. Candidate writes additionally
require `AOA_MEMO_MCP_CANDIDATE_ROOTS`; managed lifecycle supplies that exact
allowlist and the distinct candidate bearer.

If the package is installed, use the installed server entry-point procedure in `VALIDATION.md`.


## Report

State which MCP surface changed, which owner boundary was touched, which pilot
port was involved, what validation ran, and whether any durable memory write
was attempted.
