# qwen3-4b-int4-ov

- `card_id`: `mc.qwen3-4b-int4-ov`
- `scope`: current `OpenVINO/Qwen3-4B-int4-ov` GPU lane on
  `langchain-api-intel-text -> OVMS`
- `status`: `candidate`
- `profile_class`: `spark`

## Best For

- the current lowest-latency Intel-served `Qwen3` text lane on this host
- strict short control-plane contracts such as exact replies, compact JSON, and
  bounded routing
- early OVMS/OpenVINO challenger work where the main question is whether a
  modern Intel-served lane can stay fast and contract-clean

## Avoid For

- pretending it already proved a richer-answer advantage over the rest of the
  `Qwen3` family
- unanchored short semantic prompts that require the model to infer both the
  right repo and the right explanation without stronger scaffolding
- promotion over the current `llama.cpp` default without a broader packet

## Preferred Backends

- `OVMS`
- `OpenVINO`

## Validated Lanes

- `compose/tuning/intel-text.ovms-gpu-lab.yml`
- `compose/tuning/intel-text.ovms-qwen3-settings.yml`

## Candidate Lanes

- future `OpenVINO GenAI` screening for the same donor
- future `NPU` or `cw` class `Qwen3` lanes where low-latency control work is
  still the main goal

## Contract Notes

- this donor requires the `Qwen3`-specific OVMS posture rather than the bare
  generic harness: `tool_parser=hermes3`, `reasoning_parser=qwen3`, and
  `chat_template_kwargs.enable_thinking=false`
- on the current Intel 285H host it beats `OpenVINO/Qwen3-8B-int4-ov` across
  the current extended four-case packet, making it the present
  latency/control-plane winner inside the Intel-served `Qwen3` family
- explicit role-pick JSON prompts stay stable on this donor
- richer ad hoc probes such as `repo+why` or `repo-pair` are not yet strong:
  the donor can stay structurally valid while choosing the wrong repo or
  drifting semantically

## Evidence Surfaces

- [qwen3-openvino-family](/home/dionysus/src/abyss-stack/docs/model-cards/qwen3-openvino-family.md)
- `/srv/abyss-stack/Logs/runtime-benchmarks/runs/2026-04-08T160340Z__latency-single-turn__intel-text-qwen3-4b-int4-gpu-lab-extended`

## Next Test

Run one richer-answer packet that stays bounded but asks for short grounded
structured answers rather than only routing and exact-token control. Promote
this donor only if it stays clearly ahead on latency without collapsing once
the semantic load rises.
