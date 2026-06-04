# Root Routes Validator Module

- Decision ID: ABYSS-STACK-D-0055
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/root_routes.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, docs route, agent guidance
- Stack lanes: source checkout, docs and routes, decision lane
- Mechanic parents: cross-mechanic
- Guard families: validation lane, root route, design surface, entry contract
- Posture: accepted fourteenth validator-module split

## Context

After the branch-policy split, `scripts/validate_stack.py` still held root
design and entry-route checks. These checks protect the root route-card shape,
the `DESIGN.md` and `DESIGN.AGENTS.md` design law, docs front-door routing, and
the `docs/routes/START_HERE_ROUTE_CONTRACT.md` route-mode contract.

This surface is the repository front door. It routes people and agents into
the correct owner surfaces; it does not own mechanic-local contracts,
decision-index generation, or runtime execution.

## Options considered

- Keep root design and entry-route checks inside `scripts/validate_stack.py`.
- Fold them into source structure because they mention root files.
- Create a focused `scripts/validators/root_routes.py` module.

## Decision

Create `scripts/validators/root_routes.py` and move the implementations of:

- `validate_root_design_surfaces`
- `validate_entry_route_contract`

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Root route surfaces are not just required files. They encode how the runtime
substrate should be entered: where design law lives, how agents route from the
root card to district cards, where command authority is delegated, and which
route modes the README must expose.

Keeping this as a focused module makes front-door drift testable without
mixing it with mechanic topology or decision-record generated indexes.

## Consequences

- Positive: root design and start-here route contracts now have a focused
  owner module.
- Positive: direct module tests cover design-boundary drift, route-mode drift,
  and missing `START_HERE_ROUTE_CONTRACT.md` exposure.
- Positive: root validator API compatibility remains intact.
- Tradeoff: root README route-focus checks inside `validate_paths` remain a
  later split candidate because that function also carries runtime and
  governed-execution route assertions.

## Source surfaces

- `scripts/validators/root_routes.py`
- `scripts/validate_stack.py`
- `AGENTS.md`
- `DESIGN.md`
- `DESIGN.AGENTS.md`
- `CHARTER.md`
- `BOUNDARIES.md`
- `README.md`
- `docs/README.md`
- `docs/AGENTS.md`
- `docs/routes/START_HERE_ROUTE_CONTRACT.md`
- `tests/test_root_routes_validator_module.py`

## Follow-up route

Candidate next splits are decision-record surface guards or mechanics topology
contracts.
