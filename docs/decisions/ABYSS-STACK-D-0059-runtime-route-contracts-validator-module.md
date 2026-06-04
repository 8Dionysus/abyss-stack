# Runtime Route Contracts Validator Module

- Decision ID: ABYSS-STACK-D-0059
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/runtime_route_contracts.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, runtime routes, governed policy
- Stack lanes: source checkout, runtime mechanics, release/tooling
- Mechanic parents: inference-pilots, governed-execution, federation-seams, runtime-lifecycle
- Guard families: validation lane, runtime route contracts, stale path hygiene, governed policy envelope
- Posture: accepted eighteenth validator-module split

## Context

After the profile-topology split, `scripts/validate_stack.py` still held the
large `validate_paths` body. The name was narrower than the contract: the
function protected stale deployed-root references, root README route focus,
source/deployed/trial wording in runtime docs, federation handoff docs, and
the governed execution policy and canary catalog envelope.

Keeping that body in the root validator made the remaining split map harder to
read because path hygiene, route docs, and governed runtime policy were buried
inside a generic root function.

## Options considered

- Keep `validate_paths` inside `scripts/validate_stack.py` until the final root
  cleanup.
- Split only stale path scanning and leave README, runtime docs, and governed
  policy checks in the root validator.
- Create a focused `scripts/validators/runtime_route_contracts.py` module for
  the whole runtime route contract.

## Decision

Create `scripts/validators/runtime_route_contracts.py` and move the
implementation of `validate_paths` into the module.

Keep `scripts/validate_stack.py` as the compatibility entrypoint, delegating
the historical `validate_paths` function to the module.

## Rationale

The protected surface is one operational route contract, not a generic text
scan. Stale runtime roots, root README scope, source/deployed/trial vocabulary,
federation handoffs, and governed policy routing all define how a source
checkout points operators toward the deployed runtime without pretending that
source docs are live runtime proof.

Moving the full surface together preserves that meaning and keeps the root
validator focused on orchestration plus remaining transitional contracts.

## Consequences

- Positive: runtime route contracts now have a focused owner module and direct
  tests.
- Positive: `validate_stack.py` loses the large `validate_paths` body while
  retaining compatibility for existing callers.
- Positive: stale legacy runtime-root detection no longer relies on the root
  validator carrying its own allowlist entry.
- Tradeoff: the module spans README, runtime docs, federation docs, inference
  pilot docs, and governed policy templates because the route contract crosses
  those surfaces.

## Source surfaces

- `scripts/validators/runtime_route_contracts.py`
- `scripts/validate_stack.py`
- `README.md`
- `docs/runtime/PATHS.md`
- `docs/install/DEPLOYMENT.md`
- `docs/profiles/PROFILES.md`
- `docs/profiles/PROFILE_RECIPES.md`
- `docs/runtime/SERVICE_CATALOG.md`
- `docs/runtime/STORAGE_LAYOUT.md`
- `docs/operations/LIFECYCLE.md`
- `mechanics/inference-pilots/`
- `mechanics/diagnostic-spine/parts/truth-surfaces/`
- `mechanics/governed-execution/`
- `mechanics/federation-seams/parts/playbook-seam/`
- `config-templates/Configs/agent-api/governed-execution-policy.yaml`
- `config-templates/Configs/agent-api/governed-canary-catalog.json`
- `tests/test_runtime_route_contracts_validator_module.py`

## Follow-up route

Candidate next splits are inference-pilot compatibility gate language, active
topology language, or agent skill projection routes.
