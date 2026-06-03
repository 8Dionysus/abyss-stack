# AoA Evals MCP Access Plane

- Decision ID: ABYSS-STACK-D-0035
- Status: accepted
- Date: 2026-05-25
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-25
- Surface classes: MCP access plane, federation/read-model
- Stack lanes: MCP services, federation seams
- Mechanic parents: federation-seams
- Guard families: read-only access plane, MCP port confinement
- Posture: accepted evals access-plane rationale

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

It may also expose read-only runtime status, candidate packet validation, and a
read-model over stack-owned private runtime candidate exports under
`Logs/eval-exports/`. Those surfaces preflight mirror freshness, candidate
shape, and existing candidate-export records. They do not ingest into
`aoa-evals`, persist new exports, accept, score, compare, or publish evidence.

It may expose read-only find-or-propose routing that returns likely existing
eval matches and a candidate `eval_need_v1` proposal context. That route does
not approve the proposal, create source bundles, or bypass the repo-local
`aoa-evals` scaffold helper.

## Rationale

This preserves the owner split. `abyss-stack` owns the runtime adapter and MCP
service shape. `aoa-evals` owns the proof contract, bundle claims, generated
readers, runtime-candidate posture, report boundaries, and verdict authority.

## Consequences

- Agents can use `aoa_evals` without context flooding.
- The service stays stdio-only and read-only.
- Report skeletons leave verdict unset.
- Runtime evidence remains candidate-only until `aoa-evals` bundle-local review.
- Runtime status may flag missing/stale mirrors without making mirrors
  authoritative.
- Candidate validation is a pre-ingestion gate, not evidence acceptance.
- Runtime candidate export reads are private candidate routing, not review
  acceptance or proof publication.
- Find-or-propose makes eval growth easier from OS surfaces without turning MCP
  into a source writer.
- Future non-stdio exposure, write tools, proposal approval, source bundle
  creation, eval execution, verdict computation, receipt publication, or bundle
  promotion require a new decision.

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
