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
scripts/aoa-up --profile core
```

Example on Windows:

```powershell
pwsh -File scripts/aoa.ps1 up -Overlay compose/tuning/llamacpp.cpu.yml --profile core
```

`llamacpp.cpu.yml` is intentionally a placeholder overlay that proves the overlay path works without claiming a measured or production-grade CPU tuning contract.

## Intel 285H candidate overlays

- `llamacpp.intel-285h.cpu-safe.yml`
- `llamacpp.intel-285h.cpu-balanced.yml`
- `llamacpp.intel-285h.server-cache.yml`
- `llamacpp.intel-285h.kv-iq4nl-lab.yml`
- `llamacpp.intel-285h.vulkan-lab.yml`

These overlays land the current Fedora Intel seed as runnable, explicit host-fit candidates for the `Intel Core Ultra 9 285H` class.
They are intentionally additive:

- `cpu-safe` keeps CPU-first serving with `q8_0/q8_0` KV-cache settings
- `cpu-balanced` keeps CPU-first serving with `q4_0/q4_0` KV-cache settings
- `server-cache` extends a candidate lane with 8K context and prompt-cache reuse screening
- `kv-iq4nl-lab` is a lab-only cache-quant overlay to stack onto another candidate lane
- `vulkan-lab` is the first GPU validation lane and maps `/dev/dri` explicitly

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

## Machine-fit overlays

- `llamacpp.runtime-fallback.yml`

This overlay is a bounded host-fit fallback for `llama-cpp`.
It switches the container to `ghcr.io/ggml-org/llama.cpp:server` and disables SELinux relabeling for the current single-file GGUF mount posture.
`aoa-up` and related wrappers can apply it automatically when the latest machine-fit record recommends it.

## Why this directory exists

Because bounded overlays are healthier than duplicating the stack into platform forks.
