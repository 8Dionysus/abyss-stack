# AoA Evals Local Port Write-Side MCP

- Decision ID: ABYSS-STACK-D-0071
- Status: accepted
- Date: 2026-06-13
- Owner surface: `mcp/services/aoa-evals-mcp/`

## Index Metadata

- Original date: 2026-06-13
- Surface classes: MCP access plane, federation/read-model, source/runtime boundary
- Stack lanes: MCP services, federation seams, governed execution
- Mechanic parents: federation-seams, governed-execution
- Guard families: MCP port confinement, read-only access plane, source/runtime boundary
- Posture: accepted local-eval-port write-gate rationale

## Context

OS Abyss repositories now expose local `evals/` ports for repo-local eval
pressure, suite notes, report notes, and intake drafts. Agents need one access
plane that can discover those ports, inspect their status, and route missing
proof pressure through `aoa-evals` without leaving the current repository.

The risk is authority drift. If the stack MCP starts creating central bundles,
accepting evidence, computing verdicts, or writing arbitrary sibling paths, the
runtime adapter becomes a proof organ. If the MCP stays read-only everywhere,
agents still have to hand-copy local intake drafts and lose the repeatable
dry-run/write gate.

## Options considered

1. Keep `aoa-evals-mcp` fully read-only and require manual local-port writes.
2. Add central bundle creation and evidence acceptance to `aoa-evals-mcp`.
3. Add narrow write-side tools that only write repo-local `evals/` port files,
   default to dry-run, and keep central proof authority in `aoa-evals`.

## Decision

Choose option 3.

Extend `aoa-evals-mcp` with first-class local eval-port resources and tools:
workspace port listing, single-port inspection, local find-or-propose routing,
and gated writes for `eval_need_v1` intake packets, local suite notes, and
local report notes.

The write tools default to `apply=false`. When applied, they may only write
`evals/intake/*.eval_need.json`, `evals/suites/*.suite.md`,
`evals/reports/*.report.md`, and the owning port's `PORT.yaml` status
activation from `skeleton` to `active` when the same write adds first local
pressure.

## Rationale

This gives agents the practical loop the local `evals/` ports were created for:
discover a repo's local proof pressure, ask `aoa-evals` whether an existing
bounded eval route already applies, and write a local draft without escaping the
repo-local port.

The authority split stays intact. `abyss-stack` owns the runnable MCP adapter,
path confinement, CLI, tests, and smoke validation. `aoa-evals` owns proof
doctrine, central bundle shape, verdict logic, scoring, regression posture, and
the local eval-port standard. Sibling repositories own the local pressure files
that live under their own `evals/` ports.

## Consequences

- Agents can work with local `evals/` ports through one MCP surface.
- Local writes are explicit, dry-run-first, path-confined, and schema-shaped.
- Central `aoa-evals` bundle creation remains outside this MCP write surface.
- Future central write tools, evidence acceptance, verdict computation,
  regression scoring, non-stdio exposure, or writes outside sibling
  repo-local `evals/` ports require a new decision.

## Source surfaces

- `mcp/services/aoa-evals-mcp/AGENTS.md`
- `mcp/services/aoa-evals-mcp/README.md`
- `mcp/services/aoa-evals-mcp/pyproject.toml`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/core.py`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/server.py`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/cli.py`
- `mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py`
- `mcp/services/aoa-evals-mcp/tests/test_evals_mcp.py`

## Follow-up route

If central proposal promotion becomes necessary, add it first in
`aoa-evals` as a proof-organ decision and only then expose a stack MCP route
that remains subordinate to the central contract.
