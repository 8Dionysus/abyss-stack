# Inference Pilot Compatibility Validator Module

- Decision ID: ABYSS-STACK-D-0060
- Status: accepted
- Date: 2026-06-04
- Owner surface: `scripts/validators/inference_pilot_compatibility.py`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: validation guard, inference pilot, compatibility bridge
- Stack lanes: source checkout, runtime mechanics, release/tooling
- Mechanic parents: inference-pilots, governed-execution
- Guard families: validation lane, compatibility gate language, legacy metadata containment, pilot route posture
- Posture: accepted nineteenth validator-module split

## Context

After the runtime-route-contract split, `scripts/validate_stack.py` still held
two inference-pilot compatibility checks:

- `validate_local_trials_compatibility_bridge`
- `validate_inference_pilot_compatibility_gate_language`

Together these checks protect the active local-trials bridge from re-owning
legacy trial meaning, keep W0-W4 metadata contained in the preserved legacy
runner, keep LangGraph and llama.cpp promotion flows routed through preserved
compatibility gate IDs, and ensure autonomy status readouts label old pilot
indexes as legacy compatibility routes.

## Options considered

- Keep the checks in `scripts/validate_stack.py` as part of the remaining root
  source-topology surface.
- Split only the local-trials bridge check and leave LangGraph, llama.cpp, and
  autonomy-status language in the root validator.
- Create a focused `scripts/validators/inference_pilot_compatibility.py` module
  for the full compatibility surface.

## Decision

Create `scripts/validators/inference_pilot_compatibility.py` and move the
implementations of:

- `validate_local_trials_compatibility_bridge`
- `validate_inference_pilot_compatibility_gate_language`

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

The local-trials bridge, LangGraph pilot, llama.cpp pilot, and autonomy-status
readouts all protect one semantic boundary: preserved compatibility gates must
remain visible as legacy routes without becoming active topology or new proof
authority.

Splitting only one file would hide that boundary again. Keeping the whole
compatibility surface together gives future edits one place to check when a
pilot route, gate ID, or legacy trial label changes.

## Consequences

- Positive: inference-pilot compatibility now has a focused owner module and
  direct tests.
- Positive: `scripts/validate_stack.py` loses another root-owned route-language
  body while preserving historical wrapper names.
- Positive: focused tests cover bridge posture, legacy metadata containment,
  gate snippet drift, and forbidden active W4 labels.
- Tradeoff: the module spans inference-pilots and governed-execution because
  autonomy status readouts are part of the preserved pilot compatibility
  contract.

## Source surfaces

- `scripts/validators/inference_pilot_compatibility.py`
- `scripts/validate_stack.py`
- `mechanics/inference-pilots/parts/local-trials/aoa_local_ai_trials.py`
- `mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py`
- `mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-local-ai-trials`
- `mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py`
- `mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md`
- `mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py`
- `mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md`
- `mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py`
- `mechanics/governed-execution/parts/autonomy-status/README.md`
- `tests/test_inference_pilot_compatibility_validator_module.py`

## Follow-up route

Candidate next splits are active topology language or agent skill projection
routes.
