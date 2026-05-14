# compose tuning

This directory stores optional compose overlays.

## Rule

Tuning files do not replace modules, profiles, or presets.

They are layered on top of the canonical compose surface through:

- `AOA_EXTRA_COMPOSE_FILES`
- the Windows bridge `-Overlay` parameter

## Resolution rule

Relative overlay paths are resolved inside `${AOA_CONFIGS_ROOT}`.

That means:

- `compose/tuning/llamacpp.cpu.yml`
- `compose/tuning/llamacpp.intel-285h.cpu-safe.yml`
- `compose/tuning/llamacpp.intel-285h.cpu-balanced.yml`
- `compose/tuning/llamacpp.intel-285h.server-cache.yml`
- `compose/tuning/llamacpp.intel-285h.kv-iq4nl-lab.yml`
- `compose/tuning/llamacpp.intel-285h.vulkan-lab.yml`
- `compose/tuning/llamacpp.runtime-fallback.yml`

resolves to:

- `${AOA_CONFIGS_ROOT}/compose/tuning/llamacpp.cpu.yml`

## Placeholder example

- `llamacpp.cpu.yml`

Example on Linux:

```bash
export AOA_EXTRA_COMPOSE_FILES=compose/tuning/llamacpp.cpu.yml
scripts/aoa-up --profile substrate --profile local-worker
```

Example on Windows:

```powershell
pwsh -File scripts/aoa.ps1 up -Overlay compose/tuning/llamacpp.cpu.yml --profile substrate --profile local-worker
```

`llamacpp.cpu.yml` is intentionally a placeholder overlay that proves the overlay path works without claiming a measured or production-grade CPU tuning contract.

## Intel 285H candidate overlays

- `llamacpp.intel-285h.cpu-safe.yml`
- `llamacpp.intel-285h.cpu-balanced.yml`
- `llamacpp.intel-285h.server-cache.yml`
- `llamacpp.intel-285h.kv-iq4nl-lab.yml`
- `llamacpp.intel-285h.vulkan-lab.yml`
- `intel-text.ovms-gpu-lab.yml`
- `intel-text.ovms-qwen3-settings.yml`

These overlays land the current Fedora Intel baseline as runnable, explicit host-fit candidates for the `Intel Core Ultra 9 285H` class.
They are intentionally additive:

- `cpu-safe` keeps CPU-first serving with `q8_0/q8_0` KV-cache settings
- `cpu-balanced` keeps CPU-first serving with `q4_0/q4_0` KV-cache settings
- `server-cache` extends a candidate lane with 8K context and prompt-cache reuse screening
- `kv-iq4nl-lab` is a lab-only cache-quant overlay to stack onto another candidate lane
- `vulkan-lab` is the first GPU validation lane, maps `/dev/dri` explicitly, swaps `llama-cpp` to the official `ghcr.io/ggml-org/llama.cpp:server-vulkan` image seam for that packet, and carries the current best-known lab posture for this host
- `intel-text.ovms-gpu-lab` is a standalone OVMS text-generation sidecar harness for explicit model-card-driven Intel text screening, uses a conservative single-sequence GPU posture, and exposes a separate `langchain-api` on `5404`
- `intel-text.ovms-qwen3-settings` layers the official `Qwen3` OVMS settings over that harness: `tool_parser=hermes3`, `reasoning_parser=qwen3`, `cache_size=2`, `LC_OPENAI_LITERAL_COMPLETIONS=false`, and `chat_template_kwargs.enable_thinking=false`

Example on Linux:

```bash
export AOA_EXTRA_COMPOSE_FILES=compose/tuning/llamacpp.intel-285h.cpu-balanced.yml
scripts/aoa-up --profile agentic
```

Stacked cache-screening example:

```bash
export AOA_EXTRA_COMPOSE_FILES=compose/tuning/llamacpp.intel-285h.cpu-balanced.yml,compose/tuning/llamacpp.intel-285h.server-cache.yml
scripts/aoa-up --profile agentic
```

Lab-only Vulkan example:

```bash
export AOA_EXTRA_COMPOSE_FILES=compose/tuning/llamacpp.intel-285h.vulkan-lab.yml
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.vulkan-lab.yml
```

Keep these overlays in explicit benchmark or pilot use until machine-fit and reviewed runtime docs promote one of them.
At the moment, that promotion still belongs to `cpu-safe`; `vulkan-lab` is working but remains a lab-only candidate.

Standalone Intel text lab example:

```bash
scripts/aoa-sync-configs
export AOA_OVMS_TEXT_SOURCE_MODEL=OpenVINO/Qwen3-8B-int4-ov
export AOA_OVMS_TEXT_MODEL_NAME=OpenVINO/Qwen3-8B-int4-ov
podman compose \
  -f /srv/AbyssOS/abyss-stack/Configs/compose/tuning/intel-text.ovms-gpu-lab.yml \
  -f /srv/AbyssOS/abyss-stack/Configs/compose/tuning/intel-text.ovms-qwen3-settings.yml \
  up -d
scripts/aoa-qwen-check --case exact-reply --url http://127.0.0.1:5404/run
scripts/aoa-qwen-bench --profile intel \
  --url http://127.0.0.1:5404/run \
  --backend-label "langchain-api-intel-text -> ovms-openai" \
  --model-label "OpenVINO/Qwen3-8B-int4-ov" \
  --runtime-variant "OVMS text-generation sidecar on GPU" \
  --target-label "intel-text-qwen3-8b-int4-gpu-lab"
```

This harness is intentionally donor-agnostic.
Set `AOA_OVMS_TEXT_SOURCE_MODEL` and `AOA_OVMS_TEXT_MODEL_NAME` from a reviewed
model card before bringing it up.
When the donor is `Qwen3`, layer `intel-text.ovms-qwen3-settings.yml` on top so
the official OVMS parser and no-thinking settings are not lost.

## Machine-fit overlays

- `llamacpp.runtime-fallback.yml`

This overlay is a bounded host-fit fallback for `llama-cpp`.
It switches the container to `ghcr.io/ggml-org/llama.cpp:server` and disables SELinux relabeling for the current single-file GGUF mount posture.
`aoa-up` and related wrappers can apply it automatically when the latest machine-fit record recommends it.

## Why this directory exists

Because bounded overlays are healthier than duplicating the stack into platform forks.
