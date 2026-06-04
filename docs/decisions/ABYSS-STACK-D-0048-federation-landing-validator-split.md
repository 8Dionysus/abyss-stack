# Federation Landing Validator Split

- Decision ID: ABYSS-STACK-D-0048
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/federation_surface.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, federation seam, runtime docs
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: federation-seams
- Guard families: validation lane, runtime topology, route docs
- Posture: accepted federation landing split

## Context

The root validator still carried `validate_federation_landing`, a documentation
guard for the federation runtime landing. It checks config-template routes,
runtime storage/service docs, deployment instructions, profile recipes, and the
operations runbook.

This guard does not validate runtime export schemas. It protects the operator
route into federation: how the stack exposes the federation profile, route-api
sidecar, advisory checks, sibling roots, and first consumer examples.

## Decision

Move `validate_federation_landing` implementation into
`scripts/validators/federation_surface.py`.

During the extraction bridge, root compatibility preserved existing callers.
D-0063 closes that bridge and routes focused callers to the federation owner
module.

Add focused module coverage for a landing-doc route failure in
`tests/test_federation_validator_module.py`.

## Options considered

- Keep federation landing validation in `scripts/validate_stack.py`.
- Move federation landing into a separate docs-only validator module.
- Move it into `scripts/validators/federation_surface.py` while leaving runtime
  seam export guards for a later split.

## Rationale

Federation landing docs belong with the federation validator module but are a
separate slice from runtime input coverage and upstream compatibility language.
Extracting them keeps the root validator shrinking while preserving all old
error messages and release behavior.

## Consequences

- Positive: federation landing docs now share the federation owner module.
- Positive: route-api landing coverage has focused module tests.
- Positive: compatibility callers stayed stable during the extraction bridge.
- Tradeoff: memo/eval/playbook/KAG runtime seam export checks remain for later
  splits.

## Source surfaces

- `scripts/validators/federation_surface.py`
- `scripts/validate_stack.py`
- `config-templates/README.md`
- `docs/runtime/`
- `docs/install/DEPLOYMENT.md`
- `docs/profiles/`
- `docs/operations/RUNBOOK.md`
- `tests/test_federation_validator_module.py`

## Follow-up route

Candidate next federation split is runtime seam export guards for memo, eval,
playbook, and KAG.
