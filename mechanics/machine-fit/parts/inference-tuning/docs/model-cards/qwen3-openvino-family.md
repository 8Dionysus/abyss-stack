# qwen3-openvino-family

- `card_id`: `mc.qwen3-openvino-family`
- `scope`: `Qwen3` family as the preferred text-family intake surface for
  `OVMS`, `OpenVINO`, and future `OpenVINO GenAI` screening on `abyss-stack`
- `status`: `candidate`
- `profile_class`: `workhorse`

## Best For

- first serious Intel-served text challengers to the canonical `llama.cpp` lane
- explicit GPU, NPU, and future GenAI screening where official OpenVINO-ready
  artifacts matter
- keeping the Intel-serving line on a modern family instead of drifting into
  tiny or stale donors

## Avoid For

- pretending the whole family is already promoted in this stack
- replacing the canonical `llama.cpp` path without a measured packet
- using old `Qwen2*` or unrelated donor shortcuts just because they download
  faster

## Preferred Backends

- `OVMS`
- `OpenVINO`
- `OpenVINO GenAI`

## Preferred First Variants

- `OpenVINO/Qwen3-4B-int4-ov` for the current low-latency control-plane GPU
  candidate
- `OpenVINO/Qwen3-8B-int4-ov` for a heavier GPU follow-up packet once the `4B`
  lane is understood
- `OpenVINO/Qwen3-8B-int4-cw-ov` for a distinct NPU lab lane

## Deprioritized Variants

- `INT8` variants before the matching `INT4` packet is understood
- `14B` before `4B` and `8B` family fit is measured on this host

## Contract Notes

- this card treats `Qwen3` as the serious OpenVINO-side family even if it
  remains a compromise relative to broader `Qwen3.5` family ambitions
- the reason is operational fit, not doctrine: the current Intel-serving path
  needs good OpenVINO, OVMS, and GenAI compatibility more than vague family
  prestige
- official OVMS posture for `Qwen3` is not the bare generic harness; it needs
  `tool_parser=hermes3`, `reasoning_parser=qwen3`, and client-side
  `chat_template_kwargs.enable_thinking=false`
- with those official settings layered in, both `OpenVINO/Qwen3-4B-int4-ov` and
  `OpenVINO/Qwen3-8B-int4-ov` now pass the current extended four-case packet on
  the isolated `5404` lane
- `OpenVINO/Qwen3-4B-int4-ov` is the current measured family winner for
  latency-sensitive control-plane work on this host
- `OpenVINO/Qwen3-8B-int4-ov` remains the heavier family candidate, but its
  richer-answer advantage is still only a hypothesis; the present short richer
  probes do not yet prove it
- without the official `Qwen3` settings, the same donors fell into
  reasoning-style output and broke the bounded exact and routing contracts

## Variant Cards

- [qwen3-4b-int4-ov](/home/dionysus/src/abyss-stack/mechanics/machine-fit/parts/inference-tuning/docs/model-cards/qwen3-4b-int4-ov.md)
- [qwen3-8b-int4-ov](/home/dionysus/src/abyss-stack/mechanics/machine-fit/parts/inference-tuning/docs/model-cards/qwen3-8b-int4-ov.md)

## Candidate Lanes

- `compose/tuning/intel-text.ovms-gpu-lab.yml`
- `compose/tuning/intel-text.ovms-qwen3-settings.yml`

## Evidence Surfaces

- [MODEL_CARDS](/home/dionysus/src/abyss-stack/mechanics/machine-fit/parts/inference-tuning/docs/MODEL_CARDS.md)
- [PROFILE_RECIPES](/home/dionysus/src/abyss-stack/docs/PROFILE_RECIPES.md)
- [SERVICE_CATALOG](/home/dionysus/src/abyss-stack/docs/SERVICE_CATALOG.md)
- `/srv/AbyssOS/abyss-stack/Logs/runtime-benchmarks/runs/2026-04-08T160340Z__latency-single-turn__intel-text-qwen3-4b-int4-gpu-lab-extended`
- `/srv/AbyssOS/abyss-stack/Logs/runtime-benchmarks/runs/2026-04-08T154510Z__latency-single-turn__intel-text-qwen3-8b-int4-gpu-lab`
- `/srv/AbyssOS/abyss-stack/Logs/runtime-benchmarks/runs/2026-04-08T155804Z__latency-single-turn__intel-text-qwen3-8b-int4-gpu-lab-extended`

## Next Test

Run the current low-latency GPU packet with explicit environment selection:

```bash
export AOA_OVMS_TEXT_SOURCE_MODEL=OpenVINO/Qwen3-4B-int4-ov
export AOA_OVMS_TEXT_MODEL_NAME=OpenVINO/Qwen3-4B-int4-ov
podman compose \
  -f /srv/AbyssOS/abyss-stack/Configs/compose/tuning/intel-text.ovms-gpu-lab.yml \
  -f /srv/AbyssOS/abyss-stack/Configs/compose/tuning/intel-text.ovms-qwen3-settings.yml \
  up -d
scripts/aoa-qwen-check --case exact-reply --url http://127.0.0.1:5404/run
scripts/aoa-qwen-bench --profile intel --url http://127.0.0.1:5404/run --backend-label "langchain-api-intel-text -> ovms-openai" --model-label "OpenVINO/Qwen3-4B-int4-ov" --runtime-variant "OVMS text-generation sidecar on GPU" --target-label "intel-text-qwen3-4b-int4-gpu-lab"
```

After the first packet, move to a bounded richer-answer packet instead of
assuming the larger donor is already justified.

Current bounded result on the Intel 285H lab lane:

- `Qwen3-4B-int4-ov exact-reply mean_s`: `0.260`
- `Qwen3-4B-int4-ov repo-routing mean_s`: `1.416`
- `Qwen3-4B-int4-ov repo-choice mean_s`: `0.262`
- `Qwen3-4B-int4-ov json-decision mean_s`: `0.523`
- `Qwen3-4B-int4-ov overall mean_s`: `0.615`
- `Qwen3-8B-int4-ov exact-reply mean_s`: `0.551`
- `Qwen3-8B-int4-ov repo-routing mean_s`: `2.066`
- `Qwen3-8B-int4-ov repo-choice mean_s`: `0.457`
- `Qwen3-8B-int4-ov json-decision mean_s`: `1.001`
- `Qwen3-8B-int4-ov overall mean_s`: `1.019`
- both `all_passed`: `true`

This makes `Qwen3-4B-int4-ov` the current Intel-served `Qwen3` winner for
latency-sensitive bounded control work on this host.
`Qwen3-8B-int4-ov` remains a valid family candidate, but not yet a measured
winner.
