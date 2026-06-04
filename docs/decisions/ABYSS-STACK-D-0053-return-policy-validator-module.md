# Return Policy Validator Module

- Decision ID: ABYSS-STACK-D-0053
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/return_policy.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, governed execution, runtime contract
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: governed-execution, config-projection
- Guard families: validation lane, return-policy, runtime schema, render truth
- Posture: accepted twelfth validator-module split

## Context

After the machine-fit split, `scripts/validate_stack.py` still held the
return-policy runtime contract checks. These checks protect the source routes
for `Configs/agent-api/return-policy.yaml`, render-truth references to
`aoa-status --autonomy`, and runtime return policy/event schema identity.

The return-policy surface supports governed execution and runtime re-entry. It
does not create autonomous authority or bypass the existing autonomy gate.

## Options considered

- Keep return-policy checks inside `scripts/validate_stack.py`.
- Fold them into governed-execution runner validation.
- Create a focused `scripts/validators/return_policy.py` module.

## Decision

Create `scripts/validators/return_policy.py` and move the implementation of
`validate_return_runtime_contract` into it.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Return-policy contracts are a small but distinct runtime owner surface. Keeping
them in a focused validator module makes schema identity and render-truth route
drift easy to test without widening governed-runner or config-projection
behavior.

## Consequences

- Positive: return-policy config routes and schema identity have a focused
  owner module.
- Positive: direct module tests cover policy schema const drift and
  render-truth autonomy route drift.
- Positive: root validator API compatibility remains intact.
- Tradeoff: the module spans governed-execution and config-projection because
  render truth is where the return-policy mount is made visible.

## Source surfaces

- `scripts/validators/return_policy.py`
- `scripts/validate_stack.py`
- `config-templates/Configs/agent-api/return-policy.yaml`
- `mechanics/governed-execution/parts/return-policy/`
- `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`
- `tests/test_return_policy_validator_module.py`

## Follow-up route

Candidate next splits are branch/release governance or root design/route
surface guards.
