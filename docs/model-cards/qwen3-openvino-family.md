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

- `OpenVINO/Qwen3-8B-int4-ov` for the first GPU packet
- `OpenVINO/Qwen3-4B-int4-ov` for a lighter GPU packet
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
- exact-reply, compact JSON routing, and bounded repo-selection behavior still
  need to be rechecked on each concrete donor and quantization

## Candidate Lanes

- `compose/tuning/intel-text.ovms-gpu-lab.yml`

## Evidence Surfaces

- [MODEL_CARDS](/home/dionysus/src/abyss-stack/docs/MODEL_CARDS.md)
- [PROFILE_RECIPES](/home/dionysus/src/abyss-stack/docs/PROFILE_RECIPES.md)
- [SERVICE_CATALOG](/home/dionysus/src/abyss-stack/docs/SERVICE_CATALOG.md)

## Next Test

Run the first GPU packet with explicit environment selection:

```bash
export AOA_OVMS_TEXT_SOURCE_MODEL=OpenVINO/Qwen3-8B-int4-ov
export AOA_OVMS_TEXT_MODEL_NAME=OpenVINO/Qwen3-8B-int4-ov
podman compose -f /srv/abyss-stack/Configs/compose/tuning/intel-text.ovms-gpu-lab.yml up -d
scripts/aoa-qwen-check --case exact-reply --url http://127.0.0.1:5404/run
scripts/aoa-qwen-bench --profile intel --url http://127.0.0.1:5404/run --backend-label "langchain-api-intel-text -> ovms-openai" --model-label "OpenVINO/Qwen3-8B-int4-ov" --runtime-variant "OVMS text-generation sidecar on GPU" --target-label "intel-text-qwen3-8b-int4-gpu-lab"
```

If that lane looks promising, compare it against `OpenVINO/Qwen3-4B-int4-ov`
before touching promotion surfaces.
