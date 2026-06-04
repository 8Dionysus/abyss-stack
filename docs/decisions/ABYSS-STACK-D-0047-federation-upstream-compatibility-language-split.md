# Federation Upstream Compatibility Language Split

- Decision ID: ABYSS-STACK-D-0047
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/federation_surface.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, federation seam, compatibility bridge
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: federation-seams
- Guard families: validation lane, compatibility bridge, legacy boundary
- Posture: accepted federation module expansion

## Context

After the first federation module split, the remaining upstream compatibility
language guard still lived in `scripts/validate_stack.py`. It checks that the
active federation bridge document stays lightweight, that detailed legacy
values remain in `legacy/upstream-compatibility/INDEX.md`, and that runtime
configs do not inline old upstream names.

This guard belongs to the same federation owner module as runtime input
coverage because both checks protect the upstream compatibility bridge.

## Decision

Move `validate_federation_upstream_compatibility` implementation into
`scripts/validators/federation_surface.py`.

During the extraction bridge, root compatibility preserved existing callers.
D-0063 closes that bridge and routes focused callers to the federation owner
module.

Add focused coverage for the active-vs-legacy bridge value rule in
`tests/test_federation_validator_module.py`.

## Options considered

- Keep upstream compatibility language validation in `scripts/validate_stack.py`.
- Move it into a separate `upstream_compatibility.py` validator module.
- Move it into `scripts/validators/federation_surface.py` with the existing
  bridge-template and required-files guards.

## Rationale

The active bridge should stay a lightweight route, not a dump of detailed
legacy upstream identifiers. Keeping that rule in the federation module makes
the compatibility boundary explicit and keeps the root validator shrinking by
owner surface.

## Consequences

- Positive: upstream compatibility language now shares the federation owner
  module with bridge template validation.
- Positive: detailed legacy bridge value routing has focused tests.
- Positive: compatibility callers stayed stable during the extraction bridge.
- Tradeoff: federation landing docs and runtime seam export checks remain for
  later splits.

## Source surfaces

- `scripts/validators/federation_surface.py`
- `scripts/validate_stack.py`
- `mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`
- `mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md`
- `config-templates/Configs/federation/upstream-compatibility-bridge.json`
- `tests/test_federation_validator_module.py`

## Follow-up route

Candidate next federation splits are landing-doc guards or runtime seam export
guards.
