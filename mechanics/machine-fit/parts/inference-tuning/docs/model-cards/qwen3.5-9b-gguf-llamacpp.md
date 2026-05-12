# qwen3.5-9b-gguf-llamacpp

- `card_id`: `mc.qwen3.5-9b-gguf-llamacpp`
- `scope`: current text-only `Qwen3.5 9B` GGUF lane on `langchain-api -> llama.cpp`
- `status`: `reviewed`
- `profile_class`: `workhorse`

## Best For

- the current canonical local text lane on `abyss-stack`
- bounded task work on the promoted `langchain-api /run` surface
- measured Intel 285H CPU-first serving with stable contract fit
- keeping the current local-worker posture fast, explicit, and predictable

## Avoid For

- OpenVINO, OVMS, or OpenVINO GenAI screening
- claims about multimodality on the current text-only GGUF lane
- assuming the family-level agentic strengths automatically transfer to every
  runtime variant without measurement

## Preferred Backends

- `llama.cpp`

## Validated Lanes

- `compose/tuning/llamacpp.intel-285h.cpu-safe.yml`

## Candidate Lanes

- `compose/tuning/llamacpp.intel-285h.cpu-balanced.yml`
- `compose/tuning/llamacpp.intel-285h.server-cache.yml`
- `compose/tuning/llamacpp.intel-285h.vulkan-lab.yml`
- `compose/tuning/llamacpp.intel-285h.kv-iq4nl-lab.yml`

## Contract Notes

- this is the current winner because it is the best measured balance of latency,
  stability, and contract fit on the `Intel Core Ultra 9 285H` host
- the current stack uses this as a text lane, not as a claim about the whole
  wider `Qwen3.5` family
- the family may remain attractive for agentic or multimodal work at a broader
  planning level, but that is separate from the current reviewed runtime lane

## Evidence Surfaces

- [LLAMACPP_PILOT](/home/dionysus/src/abyss-stack/mechanics/inference-pilots/docs/LLAMACPP_PILOT.md)
- [MACHINE_FIT_POLICY](/home/dionysus/src/abyss-stack/mechanics/machine-fit/docs/MACHINE_FIT_POLICY.md)
- [compose tuning README](/home/dionysus/src/abyss-stack/compose/tuning/README.md)

## Next Test

Keep this card as the canonical control lane while screening Intel-served
challengers.
The next useful comparisons are not more random `llama.cpp` churn but explicit
Qwen3-based Intel text packets on OVMS/OpenVINO.
