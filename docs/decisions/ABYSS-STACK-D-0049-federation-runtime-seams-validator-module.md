# Federation Runtime Seams Validator Module

- Decision ID: ABYSS-STACK-D-0049
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/federation_runtime_seams.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, federation seam, runtime export
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: federation-seams
- Guard families: validation lane, source/runtime boundary, export candidate
- Posture: accepted eighth validator-module split

## Context

After the federation input, bridge, and landing splits, the root validator still
held memo, eval, playbook, and KAG runtime seam checks. These guards protect
runtime-facing advisory routes and bounded export candidates without promoting
sibling-owned truth into `abyss-stack`.

The eval seam also checks candidate export schemas/examples and A2A return
dry-run handoff posture, because those are the bounded runtime handoff surfaces
used by the eval-facing seam.

## Options considered

- Keep runtime seam export checks inside `scripts/validate_stack.py`.
- Add them to `scripts/validators/federation_surface.py`.
- Create a separate `scripts/validators/federation_runtime_seams.py` module for
  memo/eval/playbook/KAG seam exports and advisory routes.

## Decision

Create `scripts/validators/federation_runtime_seams.py` and move the
implementations of:

- `validate_memo_runtime_seam`
- `validate_eval_runtime_seam`
- `validate_playbook_runtime_seam`
- `validate_kag_runtime_seam`

Keep the public wrappers in `scripts/validate_stack.py`.

Add focused module tests for memo export identity, eval A2A dry-run posture, and
KAG advisory route coverage.

## Rationale

Runtime seam exports are a separate owner surface from federation landing docs
and upstream bridge configuration. Keeping them in a dedicated module keeps
the federation validator layer readable and makes future changes to export
candidate contracts easier to target.

## Consequences

- Positive: memo/eval/playbook/KAG runtime seam guards have an owner module.
- Positive: bounded export and A2A handoff posture has focused module coverage.
- Positive: compatibility callers stayed stable during the extraction bridge.
- Tradeoff: eval seam still spans governed-execution and runtime-repair
  handoff surfaces because the current owner contract treats them as one bounded
  eval-facing export route.

## Source surfaces

- `scripts/validators/federation_runtime_seams.py`
- `scripts/validate_stack.py`
- `mechanics/federation-seams/parts/*-seam/docs/`
- `mechanics/governed-execution/parts/candidate-exports/`
- `mechanics/runtime-repair/parts/a2a-return-dry-run/`
- `tests/test_federation_runtime_seams_validator_module.py`

## Follow-up route

Candidate next splits are diagnostic-spine contracts or machine-fit evidence
checks.
