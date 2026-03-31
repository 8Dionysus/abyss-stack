# LLAMACPP PILOT

## Purpose

This document defines the bounded `llama.cpp` sidecar pilot for `abyss-stack` and records the promoted runtime posture that came out of it.

The pilot originally existed to answer a narrow question:

**does a `llama.cpp` sidecar improve the local Qwen runtime posture on this machine without replacing the validated canonical Ollama path yet?**

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
- a claim that every service in the stack should immediately move off the retained control path

## Current promoted posture

The current preferred bounded local-worker path is:

`intel-full -> langchain-api-llamacpp /run -> llama.cpp + route-api`

The retained control and rollback path remains:

`intel-full -> langchain-api /run -> ollama-native + route-api`

The pilot script remains intentionally useful after promotion:
- to refresh bounded backend comparisons
- to verify the promoted sidecar posture
- to keep the control path honest without making it the default worker substrate

## What the pilot reuses

The pilot does not require a second large model download by default.

It resolves the resident Ollama `qwen3.5:9b` manifest under:

- `${AOA_STACK_ROOT}/Services/ollama/models/manifests/registry.ollama.ai/library/qwen3.5/9b`

Then it mounts the corresponding GGUF blob into the `llama.cpp` container as a read-only model file.

This keeps the pilot honest:
- same local Qwen family
- same quantized resident artifact
- different serving runtime

## Promoted and control services

When the promoted path is active, it uses two localhost-only services:

- `llama-cpp` -> `http://127.0.0.1:11435`
- `langchain-api-llamacpp` -> `http://127.0.0.1:5403/health`

The control-path services stay in place:

- `ollama` -> `http://127.0.0.1:11434`
- `langchain-api` -> `http://127.0.0.1:5401/health`

That separation preserves honest A/B comparison, rollback, and future challenger evaluation.

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

### `doctor`

- syncs source-managed configs into the runtime mirror unless `--skip-sync` is used
- confirms `aoa-doctor --preset intel-full`
- resolves the reusable GGUF model blob
- reports the base runtime health

### `up`

- ensures the base preset is up
- starts the `llama.cpp` sidecar services
- waits for `llama.cpp` and `langchain-api-llamacpp` health

### `bench`

- runs the bounded Qwen latency bench against `http://127.0.0.1:5403/run`
- labels the result as a `llama.cpp` sidecar run

### `run`

- runs a fresh Ollama baseline bench on `5401`
- runs a fresh `llama.cpp` sidecar bench on `5403`
- writes a comparison packet under:
  - `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/comparisons/llamacpp-sidecar-pilot-v1/`

### `promote`

- screens the fixed `Q4_K_M` and `Q6_K` `bartowski` candidates on the same CPU-safe sidecar posture
- chooses a winner only if the candidate stays stable and `exact-reply` is not more than `15%` slower than the fresh Ollama baseline
- runs `W0` on `http://127.0.0.1:5403/run` under `qwen-llamacpp-pilot-v1`
- runs one disposable `W4` docs fixture dry-run under `langgraph-sidecar-llamacpp-v1`
- writes the promotion packet under:
  - `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/promotions/llamacpp-promotion-gate-v1/`

### `status`

- reports the latest saved comparison ref
- reports current sidecar and baseline health

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
- `AOA_LLAMACPP_JINJA`
- `AOA_LLAMACPP_REASONING_FORMAT`

Default posture is conservative:
- official `ghcr.io/ggml-org/llama.cpp:server-openvino`
- CPU-safe sidecar defaults before any acceleration attempt:
  - `AOA_LLAMACPP_DEVICE=none`
  - `AOA_LLAMACPP_NO_OP_OFFLOAD=1`
  - `AOA_LLAMACPP_THREADS=4`
  - `AOA_LLAMACPP_THREADS_BATCH=4`
  - `AOA_LLAMACPP_THREADS_HTTP=2`
  - `AOA_LLAMACPP_CTX_SIZE=4096`
  - `AOA_LLAMACPP_BATCH_SIZE=512`
  - `AOA_LLAMACPP_UBATCH_SIZE=128`
  - `AOA_LLAMACPP_REASONING=off`
  - `AOA_LLAMACPP_THINK=none`
  - `AOA_LLAMACPP_CPUS=4.0`
  - `AOA_LLAMACPP_MEM_LIMIT=12g`
- localhost-only exposure
- separate sidecar `langchain-api`
- OVMS embeddings remain in place for the Intel pilot path

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

- fresh Ollama baseline smoke + bench
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
- `llama.cpp` is the preferred bounded local-worker path
- Ollama remains the validated control and rollback path
- any OpenVINO-side shift to OpenVINO GenAI should be reviewed separately from the `llama.cpp` promotion decision

Promotion posture still has two layers:
- `aoa-llamacpp-pilot verify` checks the promoted sidecar lane itself
- `aoa-status --autonomy --json` checks whether parity, route-api closure, federated mirrors, and W5/W6 truth status align on the deployed path
