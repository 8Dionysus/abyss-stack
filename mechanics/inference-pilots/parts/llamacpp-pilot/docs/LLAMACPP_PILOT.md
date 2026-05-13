# LLAMACPP PILOT

## Purpose

This document defines the bounded `llama.cpp` sidecar pilot for `abyss-stack` and records the promoted runtime posture that came out of it.

The pilot originally existed to answer a narrow promotion question:

**does a bounded `llama.cpp` challenger improve the local Qwen runtime posture on this machine enough to become the canonical worker path?**

That question is now answered positively for the current bounded local-worker path.

## Boundary

The pilot is:
- sidecar-only
- operator-invoked
- bounded to runtime-parity work
- allowed to compare latency and runtime behavior

The pilot is not:
- a silent replacement for the canonical local runtime
- a proof-layer quality verdict
- a claim that every other local runtime surface should reopen a second live lane

## Current promoted posture

The current preferred bounded local-worker path is:

`intel-full -> langchain-api /run -> llama.cpp + route-api`

Historical comparison artifacts may still use `sidecar`, `baseline`, or earlier service labels because the pilot family predates the canonical cutover.

The pilot script remains intentionally useful after promotion:
- to refresh bounded source-resolution and challenger artifacts
- to verify the canonical local-worker posture
- to screen explicit candidate variants without reopening a second default local lane

## What the pilot reuses

The pilot does not require a second large model download by default.

It resolves the resident local `qwen3.5:9b` manifest-backed GGUF candidate under:

- `${AOA_STACK_ROOT}/Services/ollama/models/manifests/registry.ollama.ai/library/qwen3.5/9b`

Then it mounts the corresponding GGUF blob into the `llama.cpp` container as a read-only model file.

This keeps the pilot honest:
- same local Qwen family
- same resident artifact family when the manifest-backed candidate is usable
- different serving runtime

If the resident manifest-backed GGUF candidate fails a real `llama.cpp` startup on this machine, the pilot now falls back to locally cached curated `bartowski` candidates in `Q4_K_M` then `Q6_K` order when those files are already present under:

- `${AOA_STACK_ROOT}/Logs/llamacpp/models/bartowski/`

That fallback is still local-only and bounded:
- no extra network download is required
- the active canonical runtime remains unchanged
- the sidecar only changes model file selection after an actual `llama.cpp` model-load failure

## Canonical and explicit pilot services

When the canonical promoted path is healthy, it relies on two localhost-only services:

- `llama-cpp` -> `http://127.0.0.1:11435`
- canonical `langchain-api /run` -> `http://127.0.0.1:5403/health`

Historical comparison packets may still refer to earlier sidecar and baseline service names. In the current Phase Alpha posture, those names should be read as archived artifact lineage, not as a second live control lane.

## Operator commands

Use the source-checkout script:

```bash
scripts/aoa-llamacpp-pilot doctor --preset intel-full
scripts/aoa-llamacpp-pilot up --preset intel-full
scripts/aoa-llamacpp-pilot bench --preset intel-full
scripts/aoa-llamacpp-pilot run --preset intel-full
scripts/aoa-llamacpp-pilot promote --preset intel-full
scripts/aoa-llamacpp-pilot verify --timeout 60
scripts/aoa-llamacpp-pilot status
scripts/aoa-status --autonomy
scripts/aoa-llamacpp-pilot down
```

Candidate Intel 285H overlays may be applied directly to the sidecar lane:

```bash
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.cpu-safe.yml
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.cpu-balanced.yml --overlay compose/tuning/llamacpp.intel-285h.server-cache.yml
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay compose/tuning/llamacpp.intel-285h.vulkan-lab.yml
```

The Vulkan lab overlay is self-contained for the sidecar lane: it swaps the
`llama.cpp` image to the official `ghcr.io/ggml-org/llama.cpp:server-vulkan`
build instead of trying to force `Vulkan0` through the default
`server-openvino` seam.

### `doctor`

- syncs source-managed configs into the runtime mirror unless `--skip-sync` is used
- confirms `aoa-doctor --preset intel-full`
- resolves the reusable GGUF model blob
- reports the base runtime health

### `up`

- ensures the base preset is up
- starts the `llama.cpp` sidecar services
- retries with a locally cached curated `bartowski` candidate if the resident manifest-backed GGUF candidate is rejected by `llama.cpp`
- waits for `llama.cpp` and `langchain-api-llamacpp` health

### `bench`

- runs the bounded Qwen latency bench against `http://127.0.0.1:5403/run`
- labels the result as a `llama.cpp` sidecar run

### `run`

- replays the retained comparison workflow from the pre-cutover pilot family
- should be treated as historical comparison maintenance rather than as the canonical operator path
- uses the same fallback rule as `up` if the resident manifest-backed GGUF candidate does not load cleanly in `llama.cpp`
- writes a comparison packet under:
  - `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/comparisons/llamacpp-sidecar-pilot-v1/`

### `promote`

- screens the fixed `Q4_K_M` and `Q6_K` `bartowski` candidates on the same CPU-safe sidecar posture
- chooses a winner only if the candidate stays stable and `exact-reply` is not more than `15%` slower than the fresh historical comparison basis
- runs `W0` on `http://127.0.0.1:5403/run` under `qwen-llamacpp-pilot-v1`
- runs one disposable `W4` docs fixture dry-run under `langgraph-sidecar-llamacpp-v1`
- writes the promotion packet under:
  - `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/promotions/llamacpp-promotion-gate-v1/`

### `status`

- reports the latest saved comparison ref
- reports current canonical and retained historical-comparison health when available

### `verify`

- checks the promoted `llama.cpp` sidecar path on the deployed runtime surface
- returns machine-readable JSON for bounded operator validation
- should be paired with `aoa-status --autonomy` when you need the full control-loop verdict instead of a sidecar-only check

### `down`

- stops and removes only the sidecar services
- does not tear down the canonical base stack

## Runtime knobs

The pilot accepts the upstream `llama-server` posture through environment variables such as:

- `AOA_LLAMACPP_IMAGE`
- `AOA_LLAMACPP_CTX_SIZE`
- `AOA_LLAMACPP_THREADS`
- `AOA_LLAMACPP_N_GPU_LAYERS`
- `AOA_LLAMACPP_CACHE_TYPE_K`
- `AOA_LLAMACPP_CACHE_TYPE_V`
- `AOA_LLAMACPP_CACHE_REUSE`
- `AOA_LLAMACPP_FLASH_ATTN`
- `AOA_LLAMACPP_OP_OFFLOAD`
- `AOA_LLAMACPP_JINJA`
- `AOA_LLAMACPP_REASONING_FORMAT`

Default posture is conservative:
- official `ghcr.io/ggml-org/llama.cpp:server-openvino`
- CPU-safe sidecar defaults before any acceleration attempt:
  - `AOA_LLAMACPP_DEVICE=none`
  - `AOA_LLAMACPP_OP_OFFLOAD=0`
  - `AOA_LLAMACPP_THREADS=4`
  - `AOA_LLAMACPP_THREADS_BATCH=4`
  - `AOA_LLAMACPP_THREADS_HTTP=2`
  - `AOA_LLAMACPP_CTX_SIZE=4096`
  - `AOA_LLAMACPP_BATCH_SIZE=512`
  - `AOA_LLAMACPP_UBATCH_SIZE=128`
  - `AOA_LLAMACPP_CACHE_TYPE_K=f16`
  - `AOA_LLAMACPP_CACHE_TYPE_V=f16`
  - `AOA_LLAMACPP_MMAP=1`
  - `AOA_LLAMACPP_MLOCK=0`
  - `AOA_LLAMACPP_KV_OFFLOAD=1`
  - `AOA_LLAMACPP_REASONING=off`
  - `AOA_LLAMACPP_THINK=none`
  - `AOA_LLAMACPP_CPUS=4.0`
  - `AOA_LLAMACPP_MEM_LIMIT=12g`
- localhost-only exposure
- separate sidecar `langchain-api`
- OVMS embeddings remain in place for the Intel pilot path

The current Intel 285H candidate overlay family is additive rather than promoted:
- `compose/tuning/llamacpp.intel-285h.cpu-safe.yml` for `q8_0/q8_0` CPU-safe screening
- `compose/tuning/llamacpp.intel-285h.cpu-balanced.yml` for `q4_0/q4_0` CPU-balanced screening
- `compose/tuning/llamacpp.intel-285h.server-cache.yml` for 8K context and cache reuse screening
- `compose/tuning/llamacpp.intel-285h.kv-iq4nl-lab.yml` for explicit `iq4_nl` cache trials
- `compose/tuning/llamacpp.intel-285h.vulkan-lab.yml` for first-pass Vulkan validation on this host through the dedicated `server-vulkan` image seam

Use `--overlay` on `aoa-llamacpp-pilot` when you want those settings on the explicit pilot lane.
Do not silently fold them into the canonical runtime until the measured packet says one belongs there.

As of the latest reviewed Intel 285H packet, `cpu-safe` remains the promoted live winner after the `llama.cpp` tuning-argument seam repair.
`vulkan-lab` is now a functioning lab lane with a best-known throughput posture of `N_PARALLEL=4`, `BATCH=2048`, and `UBATCH=512`, but it stays parked until a reviewed packet shows a clear promotion case.

The pilot now brings services up in two stages:
- `llama-cpp`
- health check
- `langchain-api-llamacpp`

This reduces host shock during first model load and gives a clean failure boundary before the API sidecar is attached.

If you want a more machine-specific acceleration attempt, override the pilot image or GPU-layer posture explicitly and record the outcome as a bounded runtime comparison rather than as an immediate canonical promotion.

## Artifacts

The pilot writes comparison packets under:

```text
${AOA_STACK_ROOT}/Logs/runtime-benchmarks/comparisons/llamacpp-sidecar-pilot-v1/
  latest.json
  runs/
    <timestamp>/
      model-resolution.json
      baseline.bench.stdout.txt
      baseline.bench.stderr.txt
      candidate.bench.stdout.txt
      candidate.bench.stderr.txt
      pilot.manifest.json
      comparison.json
      report.md
```

These artifacts stay runtime-local.

Promotion packets stay runtime-local too and capture:

- fresh historical comparison smoke + bench
- both quant screening outcomes
- winner selection
- `W0` verdict on the sidecar path
- disposable `W4` fixture verdict
- rollback status after sidecar teardown

## Promotion rule

A green or promising pilot does not automatically change the machine-fit record.

Promotion required:
- reviewed comparison output
- a clear recommendation that the sidecar is better for the intended bounded path
- an explicit update to machine-fit and the validated runtime docs

Current result:
- `llama.cpp` is the canonical bounded local-worker path on `5403`
- historical comparison artifacts may remain for drift review, but they do not create a second live control lane
- any OpenVINO-side shift to OpenVINO GenAI should be reviewed separately from the `llama.cpp` promotion decision

Promotion posture still has two layers:
- `aoa-llamacpp-pilot verify` checks the promoted sidecar lane itself
- `aoa-status --autonomy --json` checks whether parity, route-api closure, federated mirrors, and W5/W6 truth status align on the deployed path
