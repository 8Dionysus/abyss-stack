# Federation Surface Validator Module

- Decision ID: ABYSS-STACK-D-0046
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/federation_surface.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, federation seam, source/runtime boundary
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: federation-seams
- Guard families: validation lane, source/runtime boundary, compatibility bridge
- Posture: accepted seventh validator-module split

## Context

The root stack validator carried a federation required-files guard. That guard
checks that runtime-loaded federation config files list the source artifacts
they depend on and that the upstream compatibility bridge exposes runtime
evidence templates and playbook automation paths.

This is a federation seam, not generic root topology. It protects the boundary
where stack-owned runtime configs reference sibling-owned artifacts without
promoting those siblings' meaning into `abyss-stack`.

## Options considered

- Keep federation required-file validation in `scripts/validate_stack.py`.
- Move all federation seam checks in one large extraction.
- Move the runtime-input and bridge-template implementation into a focused
  module first, keeping broader federation landing and runtime seam checks for
  later splits.

## Decision

Move federation required runtime input coverage, upstream bridge template
validation, and active-vs-legacy bridge language validation into
`scripts/validators/federation_surface.py`.

During the extraction bridge, root compatibility functions preserved current
callers and tests, including the bridge-path parameterization. D-0063 closes
that bridge: federation constants and focused tests now route directly to
`scripts/validators/federation_surface.py`.

Add focused unit tests in `tests/test_federation_validator_module.py` for
bridge string flattening, runtime evidence template field checks, and legacy
bridge value routing.

## Rationale

This is the smallest meaningful federation split. It extracts a release-visible
source/runtime seam without pulling in every federation landing document or
runtime seam export check at once.

The upstream compatibility bridge path stayed parameterized during the first
split so the extraction did not accidentally change historical monkeypatch
semantics.

## Consequences

- Positive: federation required-file and upstream compatibility validation has
  an owner module.
- Positive: bridge-template and active-vs-legacy posture have focused module
  tests.
- Positive: compatibility callers stayed stable during the extraction bridge.
- Tradeoff: broader federation landing and runtime seam validators remain in
  `validate_stack.py` until separate owner-surface splits.
- Follow-up: extract federation landing or runtime seam checks only when their
  focused test seams are explicit.

## Source surfaces

- `scripts/validators/federation_surface.py`
- `scripts/validate_stack.py`
- `config-templates/Configs/federation/`
- `mechanics/federation-seams/parts/federation-checks/`
- `docs/validation/VALIDATOR_TOPOLOGY.md`
- `docs/validation/validator_inventory.json`
- `docs/validation/script_inventory.json`
- `docs/testing/test_inventory.json`
- `tests/test_federation_validator_module.py`
- `tests/test_federation_required_files_validator_module.py`

## Follow-up route

Candidate next splits are federation landing docs, federation runtime seam
exports, diagnostic-spine contracts, or machine-fit evidence checks.
