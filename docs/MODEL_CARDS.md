# MODEL CARDS

## Purpose

This document defines the runtime-owned model-card surface for `abyss-stack`.

Use it to record which model family or concrete runtime variant is good for what
inside this stack, on which backend, under which host-fit posture, and with
which known limits.

`MODEL_PROFILES` stays class-based.
Model cards stay family- or variant-specific.

## Decision

`abyss-stack` now keeps model-fit notes in explicit model cards instead of
leaving them spread across bench packets, chat memory, or one-off overlay names.

This keeps three things separate:

- `MODEL_PROFILES` owns class-based runtime posture such as `spark`,
  `workhorse`, `deep`, and `archive`
- model cards own family- and variant-specific operating notes, candidate
  lanes, and current fit observations
- promotion still belongs to machine-fit, pilot, profile, preset, and runtime
  benchmark surfaces rather than to the card itself

## What a model card owns

Each card should answer:

- what family or exact runtime variant it describes
- what it is good at in `abyss-stack`
- which backends or device lanes fit it best
- which contract risks or weak points matter operationally
- whether it is `lab`, `candidate`, or `reviewed`
- which measured packet or doc surface currently supports that posture
- what the next bounded test should be

## What a model card must not become

- a vendor marketing sheet
- a global leaderboard
- a proof-canon quality verdict
- a hidden promotion switch
- a substitute for `MACHINE_FIT_POLICY`, `LLAMACPP_PILOT`, or runtime bench
  packets

## Card fields

Keep cards small and operator-facing.
Prefer these fields:

- `card_id`
- `scope`
- `status`
- `best_for`
- `avoid_for`
- `preferred_backends`
- `validated_lanes`
- `candidate_lanes`
- `contract_notes`
- `evidence_surfaces`
- `next_test`

## Stepwise test loop

When screening a new model or backend lane, use this order:

1. open an existing card or create a new card before downloading or tuning
2. name the exact donor, size, quantization, and target backend in that card
3. start an isolated lane through a pilot overlay or a standalone sidecar
4. run a narrow contract check first, usually `scripts/aoa-qwen-check --case exact-reply`
5. run one bounded benchmark packet through `scripts/aoa-qwen-bench` or `scripts/aoa-llamacpp-pilot`
6. record whether the result is `lab`, `candidate`, `reviewed`, or rejected
7. only then consider machine-fit or profile promotion

If the lane is OVMS/OpenVINO/OpenVINO GenAI-based, keep the donor explicit in
environment variables or operator notes.
Do not let a donor-specific overlay quietly choose the model on your behalf.

## Current cards

- [qwen3.5-9b-gguf-llamacpp](/home/dionysus/src/abyss-stack/docs/model-cards/qwen3.5-9b-gguf-llamacpp.md)
- [qwen3-openvino-family](/home/dionysus/src/abyss-stack/docs/model-cards/qwen3-openvino-family.md)

## Relationship to existing docs

- `MODEL_PROFILES` says what class of model a lane belongs to
- `PROFILE_RECIPES` says how to bring that lane up and test it
- `RUNTIME_BENCH_POLICY` says how to capture the evidence packet
- `LLAMACPP_PILOT` and `MACHINE_FIT_POLICY` say when a candidate lane becomes
  reviewed
