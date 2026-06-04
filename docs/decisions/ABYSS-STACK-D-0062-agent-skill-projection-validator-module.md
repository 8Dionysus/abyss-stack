# Agent Skill Projection Validator Module

- Decision ID: ABYSS-STACK-D-0062
- Status: accepted
- Date: 2026-06-04
- Owner surface: `scripts/validators/agent_skill_projection.py`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: validation guard, agent skill projection, local overlay
- Stack lanes: source checkout, agent surface, release/tooling
- Mechanic parents: diagnostic-spine
- Guard families: validation lane, skill projection, overlay skill install, sibling canon target
- Posture: accepted twenty-first validator-module split

## Context

After the active-topology-language split, `scripts/validate_stack.py` still
held the repo-local agent skill projection body and the overlay skill install
helpers used by diagnostic-spine validation.

Those checks protect one route: `.agents/skills` is a local projection surface,
while canonical skill truth remains in sibling `aoa-skills`. Most projected
skills must point at `/srv/AbyssOS/aoa-skills/.agents/skills/<name>` as symlinks
or checkout-safe target files; local overlays such as
`abyss-self-diagnostic-spine` must remain explicit directories with `SKILL.md`.

## Options considered

- Keep skill projection checks inside `scripts/validate_stack.py`.
- Move only `.agents/skills` symlink checks and leave diagnostic overlay install
  helpers in the root validator.
- Create a focused `scripts/validators/agent_skill_projection.py` module for
  projection checks and overlay install validation.

## Decision

Create `scripts/validators/agent_skill_projection.py` and move the agent skill
projection implementation plus overlay install helpers into the module.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers and as the callback adapter for diagnostic-spine validation.

## Rationale

Skill projection is not general source topology. It is a boundary between
repo-local agent overlays and sibling skill canon. Keeping symlink target
checks, checkout-safe target files, local overlay directories, and diagnostic
overlay install validation together gives that boundary one owner.

This also prevents future diagnostic-spine edits from silently redefining where
skill truth lives.

## Consequences

- Positive: agent skill projection now has a focused owner module and direct
  tests.
- Positive: `scripts/validate_stack.py` no longer owns skill projection target
  constants or overlay install helper bodies.
- Positive: focused tests cover current repo validity, missing projection root,
  bad symlink targets, checkout-safe target files, local overlay `SKILL.md`,
  and diagnostic overlay expected-target files.
- Tradeoff: the module is also used by diagnostic-spine validation because
  diagnostic overlay installs are part of the same skill projection boundary.

## Source surfaces

- `scripts/validators/agent_skill_projection.py`
- `scripts/validate_stack.py`
- `.agents/skills/AGENTS.md`
- `.agents/skills/abyss-self-diagnostic-spine/SKILL.md`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`
- `scripts/validators/diagnostic_spine.py`
- `tests/test_agent_skill_projection_validator_module.py`

## Follow-up route

Root validator now primarily retains release orchestration, constants, helper
wrappers, and compatibility entrypoints for extracted modules.
