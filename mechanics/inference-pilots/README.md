# Inference Pilots Mechanic

## Mechanic card

Inference pilots are the mechanic for bounded local model experiments,
promotion loops, benchmark evidence, and adopted local-worker paths.

### Trigger

Use this package when changing llama.cpp, Qwen, OVMS, LangGraph, local trial,
benchmark, model card, or winner-promotion surfaces.

### abyss-stack owns

- local inference runtime wrappers
- public-safe trial and benchmark contracts
- model profile and card routing
- runtime winner-promotion posture
- bounded local-worker deployment support

### Stronger owner split

Model files, hardware behavior, upstream inference engines, and owner-authored
evaluation truth remain outside this repository. `aoa-evals` owns portable eval
truth when a claim becomes evaluation doctrine.

### Inputs

Machine-fit records, model cards, compose tuning overlays, public-safe trial
packets, benchmark results, and operator-selected profiles.

### Outputs

Pilot commands, benchmark indexes, bounded worker routes, promotion candidates,
and runtime evidence refs.

### Must not claim

- a model is generally best from one local run
- a pilot is production-ready without the promoted live check
- benchmark evidence replaces eval-owner truth
- a source card proves live endpoint availability

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [machine-fit](../machine-fit/README.md) for host capability and
[governed-execution](../governed-execution/README.md) when a pilot becomes a
reviewable local-worker path.

## Active route

Current source surfaces stay in `docs/`, `scripts/`, `compose/tuning/`,
`docs/model-cards/`, package benchmark surfaces under
`mechanics/inference-pilots/parts/local-trials/`, and package tests under
`mechanics/inference-pilots/parts/local-trials/tests/`. Preserved W5/W6 wave surfaces now stay
under `legacy/` with quiet root bridge commands for operator compatibility.
