# Root Validator Wrapper Tail Removal

- Decision ID: ABYSS-STACK-D-0063
- Status: accepted
- Date: 2026-06-04
- Owner surface: `scripts/validate_stack.py`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: validation topology, root orchestrator
- Stack lanes: source checkout, release/tooling
- Mechanic parents: diagnostic-spine, runtime-lifecycle, federation-seams
- Guard families: validation lane, source topology, test topology, script topology
- Posture: accepted compatibility-tail removal

## Context

D-0040 through D-0062 extracted coherent validator owner surfaces from
`scripts/validate_stack.py` while keeping public root wrapper functions as a
temporary bridge for existing tests and route cards.

That bridge kept refactoring safe during extraction, but after the focused
modules existed it became stale topology. Tests could still teach
`validate_stack.validate_*` as if the root validator owned each contract, and
current docs still described wrapper compatibility as a repair route.

## Options considered

- Keep the public root wrappers indefinitely for direct callers.
- Leave wrappers in place but stop mentioning them in docs.
- Remove the public wrapper functions, route tests to owner modules directly,
  and keep `scripts/validate_stack.py` as a command orchestrator only.

## Decision

Remove the public compatibility wrapper functions from
`scripts/validate_stack.py`.

`scripts/validate_stack.py` remains the source-fast and release entrypoint. It
owns execution order, runtime Configs mirror mode, deployed parity CLI routing,
and private glue callbacks for module calls. Focused validation behavior and
validation manifests belong in `scripts/validators/*`, and focused tests call
those modules directly.

## Rationale

The root validator is a route for running the stack-wide check, not the owner
of every surface it invokes. Leaving wrapper APIs after extraction would make
future changes patch the wrong boundary and would keep old call paths alive
after their safety purpose ended.

Removing the wrappers makes the current topology match the actual owner model:
modules hold contracts, root orchestration runs them, and inventories name the
module that should be fixed.

## Consequences

- Positive: focused tests now route to validator modules instead of root
  compatibility functions.
- Positive: `scripts/validate_stack.py` no longer exposes public
  `validate_*` wrapper APIs for extracted owner surfaces.
- Positive: validation, script, test, and diagnostic catalog routes use
  owner-shaped test filenames instead of `test_validate_stack_*` tails.
- Positive: owner modules hold their validation constants and manifests instead
  of using the root entrypoint as a configuration warehouse.
- Tradeoff: ad hoc callers that imported root wrapper functions must move to
  the focused validator module or use the `scripts/validate_stack.py` CLI.
- Follow-up: do not reintroduce root wrapper APIs when adding new validator
  modules.

## Source surfaces

- `scripts/validate_stack.py`
- `scripts/validators/`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `docs/testing/test_inventory.json`
- `tests/test_source_topology_validator_modules.py`
- `tests/test_federation_required_files_validator_module.py`
- `tests/test_questbook_surface_contracts.py`
- `tests/test_sync_parity_entrypoint_contracts.py`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_surface_validator.py`

## Follow-up route

Future validator changes should add behavior to the focused owner module and
wire it through root orchestration without adding compatibility wrapper
functions to `scripts/validate_stack.py`.
