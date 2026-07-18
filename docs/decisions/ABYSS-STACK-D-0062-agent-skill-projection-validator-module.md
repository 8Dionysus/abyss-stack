# Agent Skill Projection Validator Module

- Decision ID: ABYSS-STACK-D-0062
- Status: amended
- Amended by: `ABYSS-STACK-D-0080-diagnostic-skill-owner-home.md`
- Date: 2026-06-04
- Owner surface: `scripts/validators/agent_skill_projection.py`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: validation guard, agent skill projection, local overlay
- Stack lanes: source checkout, agent surface, release/tooling
- Mechanic parents: diagnostic-spine
- Guard families: validation lane, skill projection, overlay skill install, sibling canon target
- Posture: amended validator-module split

## Context

After the active-topology-language split, `scripts/validate_stack.py` still
held the repo-local agent skill projection body and the overlay skill install
helpers used by diagnostic-spine validation.

Those checks protect one route: `.agents/skills` is a local projection surface,
while canonical shared skill truth remains in sibling `aoa-skills`. Projected
skills must point at `/srv/AbyssOS/aoa-skills/.agents/skills/<name>` as symlinks
or checkout-safe target files.

`ABYSS-STACK-D-0080` later moved the owner-specific diagnostic procedure to
`skills/abyss-self-diagnostic-spine` and removed the local-directory exception.

## Options considered

- Keep skill projection checks inside `scripts/validate_stack.py`.
- Move only `.agents/skills` symlink checks and leave diagnostic overlay install
  helpers in the root validator.
- Create a focused `scripts/validators/agent_skill_projection.py` module for
  projection checks and overlay install validation.

## Decision

Originally, create `scripts/validators/agent_skill_projection.py` and move the
agent skill projection implementation plus overlay install helpers into the
module.

Under the D-0080 amendment, keep only the shared projection checks in this
module. `scripts/validate_stack.py` remains the compatibility entrypoint for
existing callers but is no longer a callback adapter for diagnostic-spine
validation. The diagnostic owner package is validated directly by
`scripts/validators/diagnostic_spine.py`.

## Rationale

Skill projection is not general source topology. It is a transitional boundary
between repo-local shared projections and sibling skill canon. Keeping symlink
target checks and checkout-safe target files together gives that remaining
boundary one owner; owner-specific packages do not belong in it.

This also prevents future diagnostic-spine edits from silently redefining where
skill truth lives.

## Consequences

- Positive: agent skill projection now has a focused owner module and direct
  tests.
- Positive: `scripts/validate_stack.py` no longer owns skill projection target
  constants or overlay install helper bodies.
- Positive: focused tests cover current repo validity, missing projection root,
  bad symlink targets, and checkout-safe target files.
- Amendment: diagnostic-spine validation now checks the canonical owner package
  directly instead of using this projection module as an install callback.

## Source surfaces

- `scripts/validators/agent_skill_projection.py`
- `scripts/validate_stack.py`
- `.agents/skills/AGENTS.md`
- `skills/abyss-self-diagnostic-spine/SKILL.md`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`
- `scripts/validators/diagnostic_spine.py`
- `tests/test_agent_skill_projection_validator_module.py`

## Follow-up route

Root validator now primarily retains release orchestration, constants, helper
wrappers, and compatibility entrypoints for extracted modules. The remaining
shared projection is retired only after its global OS replacements preserve
functional discovery.
