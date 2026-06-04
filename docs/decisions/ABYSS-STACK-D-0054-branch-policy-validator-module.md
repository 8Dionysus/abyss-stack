# Branch Policy Validator Module

- Decision ID: ABYSS-STACK-D-0054
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/branch_policy.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, governance route, source/runtime boundary
- Stack lanes: source checkout, docs and routes, release/tooling
- Mechanic parents: cross-mechanic
- Guard families: validation lane, branch policy, release governance, source/runtime boundary
- Posture: accepted thirteenth validator-module split

## Context

After the return-policy split, `scripts/validate_stack.py` still held branch
policy checks. These checks protect the route from `CONTRIBUTING.md` into
`docs/governance/BRANCH_POLICY.md`, the canonical `main`-only posture, branch
retirement language, and the distinction between source checkout truth and
runtime checkout state.

The branch-policy surface is governance, not mechanics topology. It decides how
source work lands and retires; it does not certify runtime health or merge live
drift back into source by implication.

## Options considered

- Keep branch-policy checks inside `scripts/validate_stack.py`.
- Fold them into source hygiene because the rule references source/runtime
  checkout boundaries.
- Create a focused `scripts/validators/branch_policy.py` module.

## Decision

Create `scripts/validators/branch_policy.py` and move the implementation of
`validate_branch_policy` into it.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Branch policy protects release governance and source truth posture. It should
stay near validation command authority, but not inside source hygiene: stale
path checks detect unsafe strings, while branch governance defines how a patch
becomes durable `main` truth and how old topic branches are retired.

## Consequences

- Positive: branch-policy drift now has a focused owner module.
- Positive: direct module tests cover CONTRIBUTING route drift and canonical
  `main` posture drift.
- Positive: root validator API compatibility remains intact.
- Tradeoff: the module is small, but its boundary is intentionally governance
  rather than mechanic-local.

## Source surfaces

- `scripts/validators/branch_policy.py`
- `scripts/validate_stack.py`
- `CONTRIBUTING.md`
- `docs/governance/BRANCH_POLICY.md`
- `tests/test_branch_policy_validator_module.py`

## Follow-up route

Candidate next splits are root design/entry route contracts or mechanics
topology contracts.
