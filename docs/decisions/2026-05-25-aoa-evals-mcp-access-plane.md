# AoA Evals MCP Access Plane

Status: accepted
Date: 2026-05-25

## Context

`aoa-evals` is the bounded proof organ for OS Abyss. Agents need a compact way
to select and inspect eval bundles, generated readers, runtime-candidate
templates, and report skeletons without loading the whole repository into
prompt context.

MCP services belong in `abyss-stack`, but proof meaning belongs in `aoa-evals`.

## Options considered

1. Keep eval access as direct repository reads only.
2. Implement an eval service in `abyss-stack` that defines its own proof
   contract.
3. Let `aoa-evals` define the MCP contract while `abyss-stack` implements the
   stdio service as a read-only access-plane adapter.

## Decision

Choose option 3.

Add `mcp/services/aoa-evals-mcp/` as the stack-owned runnable MCP package for
the stable Codex server name `aoa_evals`.

The service reads source/generated `aoa-evals` surfaces or an explicitly
configured approved mirror. It exposes resources, tools, and prompts for
selection, inspection, expansion, comparison, runtime evidence templates, and
candidate-only report skeletons.

## Rationale

This preserves the owner split. `abyss-stack` owns the runtime adapter and MCP
service shape. `aoa-evals` owns the proof contract, bundle claims, generated
readers, runtime-candidate posture, report boundaries, and verdict authority.

## Consequences

- Agents can use `aoa_evals` without context flooding.
- The service stays stdio-only and read-only.
- Report skeletons leave verdict unset.
- Runtime evidence remains candidate-only until `aoa-evals` bundle-local review.
- Future non-stdio exposure, write tools, eval execution, verdict computation,
  receipt publication, or bundle promotion require a new decision.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/aoa-evals-mcp/AGENTS.md`
- `mcp/services/aoa-evals-mcp/DESIGN.md`
- `mcp/services/aoa-evals-mcp/README.md`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/core.py`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/server.py`
- `aoa-evals:docs/architecture/AOA_EVALS_MCP_CONTRACT.md`

## Follow-up route

Run the service-local validation, stack validation, and Codex-plane smoke after
the shared-root renderer wires `aoa_evals`.
