# qwen3-8b-int4-ov

- `card_id`: `mc.qwen3-8b-int4-ov`
- `scope`: current `OpenVINO/Qwen3-8B-int4-ov` GPU lane on
  `langchain-api-intel-text -> OVMS`
- `status`: `candidate`
- `profile_class`: `workhorse`

## Best For

- the heavier `Qwen3` GPU candidate when we want more family headroom than `4B`
- continued OVMS/OpenVINO screening after the low-latency `4B` lane is already
  understood
- future richer-answer packets where a larger donor may still justify its
  latency cost

## Avoid For

- assuming it already beats `Qwen3-4B-int4-ov` on short structured contracts
- promotion into a latency-sensitive control-plane lane on current evidence
- treating model size alone as proof of better contract fit

## Preferred Backends

- `OVMS`
- `OpenVINO`

## Validated Lanes

- `compose/tuning/intel-text.ovms-gpu-lab.yml`
- `compose/tuning/intel-text.ovms-qwen3-settings.yml`

## Candidate Lanes

- future `OpenVINO GenAI` work where `Qwen3-8B` remains operationally attractive
- distinct `NPU` or `cw` `Qwen3` lanes that need a larger family donor than `4B`

## Contract Notes

- this donor also needs the same `Qwen3`-specific OVMS posture rather than the
  bare generic harness
- it passes the current extended four-case packet, so it remains a serious
  Intel-served challenger rather than a rejected donor
- on present evidence it is slower than `Qwen3-4B-int4-ov` on all four current
  packet cases
- explicit role-pick JSON prompts stay stable on this donor, but ad hoc richer
  probes are still noisy; the larger donor has not yet earned a proven
  short-answer advantage on this host

## Evidence Surfaces

- [qwen3-openvino-family](/home/dionysus/src/abyss-stack/mechanics/machine-fit/parts/inference-tuning/docs/model-cards/qwen3-openvino-family.md)
- `/srv/AbyssOS/abyss-stack/Logs/runtime-benchmarks/runs/2026-04-08T155804Z__latency-single-turn__intel-text-qwen3-8b-int4-gpu-lab-extended`

## Next Test

Do not promote this donor on size or intuition alone. Give it one bounded
richer-answer packet that `4B` is likely to strain on, and only keep it ahead
if that extra semantic headroom shows up clearly enough to justify the slower
lane.
