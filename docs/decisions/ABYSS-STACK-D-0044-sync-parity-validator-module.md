# Sync Parity Validator Module

- Decision ID: ABYSS-STACK-D-0044
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/sync_parity.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, source/runtime boundary, release parity
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: config-projection
- Guard families: validation lane, source/runtime boundary, parity check
- Posture: accepted fifth validator-module split

## Context

The release lane depends on a source-to-Configs parity guard. The root validator
enumerates sync-managed source files, verifies that the config-projection sync
script names those managed items, checks runtime Configs mirror posture, and
compares source files against a deployed or synthetic Configs root.

Those checks are not generic source topology. They protect a specific
source/runtime boundary: what the source checkout projects into runtime
Configs and how release validation proves that projection has not drifted.
That boundary includes stack-owned MCP packages and root contract schemas
because live MCP user units execute from `Configs/mcp` and deployed graph
validation resolves `Configs/schemas`.

## Options considered

- Keep sync and parity logic inside `scripts/validate_stack.py`.
- Move sync-managed item authority into a standalone manifest immediately.
- Move implementation into a focused module and keep root compatibility only
  as a temporary extraction bridge.

## Decision

Move sync-managed enumeration, sync coverage checks, runtime Configs mirror
checks, and deployed parity comparison into
`scripts/validators/sync_parity.py`.

During the extraction bridge, root compatibility functions preserved
release-check behavior and the existing parity test seams. D-0063 closes that
bridge: sync/parity constants and focused tests now route directly to
`scripts/validators/sync_parity.py` while `scripts/validate_stack.py` keeps only
the CLI orchestration call path.

Add focused unit tests in `tests/test_sync_parity_validator_module.py` for the
module-level file iterator and deployed parity comparison.

## Rationale

This split isolates a release-critical source/runtime boundary without changing
release semantics. It also makes the synthetic Configs parity route easier to
reason about because the parity implementation now has an owner module.

Keeping the sync manifest in the root preserved the first-slice contract until
the later owner-constant migration moved it into `sync_parity.py`.

## Consequences

- Positive: source-to-Configs parity has an owner module.
- Positive: sync-managed file filtering and deployed drift detection now have
  focused module tests.
- Positive: MCP service code and root schemas cannot remain silently outside
  source-to-Configs parity while their live consumers use deployed paths.
- Positive: `release_check.py` keeps the same root validation call path.
- Tradeoff: the first slice left sync-managed item constants in the root until
  the later owner-constant migration completed.
- Follow-up: a future manifest decision can promote sync-managed item authority
  after the root validator split stabilizes.

## Source surfaces

- `scripts/validators/sync_parity.py`
- `scripts/validate_stack.py`
- `scripts/release_check.py`
- `mechanics/config-projection/parts/sync/`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `docs/testing/test_inventory.json`
- `tests/test_sync_parity_validator_module.py`
- `tests/test_sync_parity_entrypoint_contracts.py`

## Follow-up route

Candidate next splits are federation seams, diagnostic-spine contracts,
machine-fit evidence checks, or questbook validation.

## Review note: 2026-07-13

Live verification of the decision-graph source-posture repair showed that
`aoa-sync-configs` projected the graph builder under `scripts/` but omitted the
MCP package that calls it and the schemas that validate it. The sync-managed
set now includes `mcp/` and `schemas/`, preserving the existing non-destructive
default and keeping restart as a separate lifecycle action.
