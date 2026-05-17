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
- Qwen3.5 prompt-cache behavior is now a measured tuning risk for the
  `llama.cpp` GGUF lane because recent upstream reports and current local logs
  both show hybrid/SWA-style full prompt re-processing signatures; cache changes
  must go through a bounded packet before promotion

## Evidence Surfaces

- [LLAMACPP_PILOT](../../../../../../mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md)
- [LLAMACPP_TUNING_RESEARCH_2026_05](../../../../../../mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_TUNING_RESEARCH_2026_05.md)
- [MACHINE_FIT_POLICY](../../../fit-record/docs/MACHINE_FIT_POLICY.md)
- [compose tuning README](../../../../../../compose/tuning/README.md)

## Next Test

Keep this card as the canonical control lane while screening explicit candidate
lanes.
The next useful comparisons are bounded `llama.cpp` tuning packets for KV-cache
quantization and prompt-cache reuse, plus explicit Qwen3-based Intel text
packets on OVMS/OpenVINO.
