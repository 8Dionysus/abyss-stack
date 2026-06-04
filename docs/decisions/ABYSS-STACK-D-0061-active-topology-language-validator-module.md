# Active Topology Language Validator Module

- Decision ID: ABYSS-STACK-D-0061
- Status: accepted
- Date: 2026-06-04
- Owner surface: `scripts/validators/active_topology_language.py`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: validation guard, active topology language, route-api bridge
- Stack lanes: source checkout, runtime mechanics, release/tooling
- Mechanic parents: federation-seams, inference-pilots
- Guard families: validation lane, active topology wording, RPG runtime projection, route-api compatibility bridge
- Posture: accepted twentieth validator-module split

## Context

After the inference-pilot compatibility split, `scripts/validate_stack.py`
still held `validate_active_topology_language`. That body protected a mixed
but coherent language boundary: old phase/wave/seed terms must not return as
active topology, RPG runtime projection must point at the current
Agents-of-Abyss runtime-projection part, and `route-api` must expose clean
active playbook routes while preserving compatibility bridge routes for old
callers.

Keeping those checks in the root validator made it unclear that this was one
route-language contract rather than miscellaneous text scanning.

## Options considered

- Keep active topology wording checks inside `scripts/validate_stack.py`.
- Split only the text-wording bans and leave route-api bridge checks in the
  root validator.
- Create a focused `scripts/validators/active_topology_language.py` module for
  the full active/legacy language boundary.

## Decision

Create `scripts/validators/active_topology_language.py` and move the
implementation of `validate_active_topology_language` into the module.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

The protected surface is the current source topology's vocabulary. Retired
phase, wave, seed, and activation terms are allowed as archive/provenance only
when they do not masquerade as active runtime topology. The route-api bridge
checks belong with that same boundary because they define the clean active
routes and the compatibility routes side by side.

Keeping this surface together makes future route renames safer: the owner
module can decide whether a term is active, compatibility, or legacy rather
than scattering that decision through the root validator.

## Consequences

- Positive: active topology language now has a focused owner module and direct
  tests.
- Positive: `scripts/validate_stack.py` loses another route-language body
  while preserving the historical wrapper name.
- Positive: focused tests cover retired phase headings, RPG legacy wave refs,
  frontend `seed` status drift, old playbook activation allowlists, upstream
  memo bridge routes, and route-api active playbook bridge routes.
- Tradeoff: the module spans ROADMAP, inference-pilot docs, federation docs,
  RPG runtime generated surfaces, route-api source, and federation config
  templates because active/legacy wording crosses those surfaces.

## Source surfaces

- `scripts/validators/active_topology_language.py`
- `scripts/validate_stack.py`
- `ROADMAP.md`
- `mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md`
- `mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md`
- `mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md`
- `mechanics/federation-seams/parts/rpg-runtime/`
- `mechanics/inference-pilots/parts/local-trials/`
- `config-templates/Configs/federation/aoa-playbooks.yaml`
- `config-templates/Configs/federation/upstream-compatibility-bridge.json`
- `config-templates/Services/route-api/app/main.py`
- `tests/test_active_topology_language_validator_module.py`

## Follow-up route

The next remaining root-owned split candidate is agent skill projection routes.
