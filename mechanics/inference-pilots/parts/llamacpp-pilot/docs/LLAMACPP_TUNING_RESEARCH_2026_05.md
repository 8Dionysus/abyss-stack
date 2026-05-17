# LLAMACPP TUNING RESEARCH 2026-05

## Status

This is a research and experiment-routing note for the current
`qwen3.5:9b -> llama.cpp -> langchain-api` local-worker lane.

It is not a promotion packet, not a live-service receipt, and not a request to
restart speech, dictation, TTS, or unrelated host services.

Use it to choose the next bounded `llama.cpp` tuning experiment and to avoid
turning a cache or zram knob into an unmeasured production default.

## Local Baseline Snapshot

Captured on the operator machine at `2026-05-14T20:23:34-06:00`.

Current live `llama-cpp` server:

- image lane: `ghcr.io/ggml-org/llama.cpp:server-openvino`
- server build: `b9144-4c1c3ac09`
- model alias: `qwen3.5:9b`
- model mount: `/models/qwen3.5-9b.gguf`
- context: `4096`
- slots: `1`
- threads: `12`
- batch / ubatch: `384 / 128`
- KV cache type: `q8_0 / q8_0`
- cache RAM limit: `8192 MiB`
- cache reuse: `0`
- mmap enabled, mlock disabled
- CPU-first posture: `LLAMA_ARG_DEVICE=none`, `LLAMA_ARG_N_GPU_LAYERS=0`

Current memory snapshot:

- RAM: `30 GiB` total, `22 GiB` used, `8.2 GiB` available
- zram swap: `15.4 GiB` disk, `14.2 GiB` data, `9.8 GiB` compressed,
  `9.9 GiB` memory used, `lzo-rle`
- memory PSI: `some/full avg10=0.00 avg60=0.00 avg300=0.00`
- `llama-cpp` container RSS: about `3.2 GiB` with a `15.03 GiB` cgroup limit
- current Prometheus gauges: prompt throughput about `12.39 tok/s`,
  generation throughput about `5.22 tok/s`

Current prompt-cache behavior:

- repeated prompts can restore checkpoints around `118`, `605`, and `606`
  tokens, so prompt caching is not globally dead
- short prompts also repeatedly log full prompt re-processing because of
  missing cache data, with the server itself pointing at SWA or
  hybrid/recurrent memory as the likely reason
- prompt-cache update cost in the sampled logs ranged from about `38 ms` to
  `349 ms`

The immediate conclusion is narrow: the memory problem is not solved by simply
enlarging zram or context. The first useful work is to reduce or reshape the
active model working set, then prove whether prompt-cache knobs actually help
this Qwen3.5 GGUF lane.

## Fresh Upstream Signals

### llama.cpp server knobs

The current `llama-server` documentation and local help expose the knobs this
stack already needs for bounded experiments:

- `--cache-type-k` and `--cache-type-v` for KV cache quantization
- `--cache-ram` for maximum server cache RAM
- `--cache-reuse` for KV-shift prompt-cache reuse
- `--cache-idle-slots` with unified KV and cache RAM
- `/metrics` for prompt/generation throughput and request pressure
- `/slots` plus `--slot-save-path` for slot cache save/restore
- `--sleep-idle-seconds` for idle sleeping in builds that expose the flag

The current compose module already carries most of these through `LLAMA_ARG_*`
environment variables. `--sleep-idle-seconds` appears in this image's local
help, but the help output does not advertise a `LLAMA_ARG_SLEEP_IDLE_SECONDS`
environment mapping. Treat sleep-idle as a command-line or entrypoint change
until a canary proves the environment mapping works.

### Qwen3.5-specific cache risk

The upstream Qwen3.5 card describes the 9B model as a hybrid architecture with
Gated DeltaNet and gated attention, a native `262,144` token context, default
thinking behavior, and serving guidance that recommends modern serving engines
for production or high throughput. It also notes that text-only serving can
free memory for additional KV cache in vLLM.

That matters locally because this stack is using a text-only GGUF lane on
`llama.cpp`, not the recommended high-throughput serving setup. The family is
still attractive, but prompt-cache and long-context behavior have to be proven
on the actual GGUF/backend pair.

Current `llama.cpp` GitHub issues are also a useful community signal, not proof
of our exact failure mode. Multiple recent Qwen3.5 or hybrid-memory reports
describe forced full prompt re-processing, prompt-cache state drift, or cache
regressions. Our live logs contain the same class of server warning, so cache
experiments should watch for correctness and latency, not only RSS.

### OpenVINO / OVMS lane

OpenVINO Model Server 2026 docs show current LLM serving through OpenAI-compatible
endpoints with continuous batching and paged attention. They also expose LLM
parameters such as `cache_size`, `reasoning_parser`, and `tool_parser`, and the
client docs include OpenAI embeddings and Cohere rerank APIs.

This keeps OVMS relevant for two separate lanes:

- embeddings/rerank sidecars that should stay on-demand or tightly bounded
- explicit Intel text-generation sidecars that must be compared against the
  canonical `llama.cpp` lane before promotion

It does not mean the current `llama.cpp` text lane should be silently replaced.
The right route is the existing `intel-text.ovms-*` lab harness plus Qwen checks
and bench packets.

### zram and cgroup controls

Kernel zram docs show useful mechanisms beyond "make zram bigger": runtime
statistics, compression algorithm selection at setup time, memory limits, idle
page marking, optional writeback, writeback budgets, compressed writeback, and
recompression when the kernel is built with the required features.

The local zram device currently has:

- primary algorithm `lzo-rle`
- available algorithms including `zstd`
- no backing device
- writeback disabled
- no active zram memory limit

Systemd resource control gives a separate layer: `MemoryHigh=` is the throttle
mechanism, `MemoryMax=` is the last defense, and `MemorySwapMax=` caps swap use.
Those are better for containing optional services than global zram expansion,
but they must not be applied blindly to speech, dictation, or the currently
interactive model lane.

## Experiment Ladder

### E0: reproducible baseline packet

Before changing knobs, capture a small packet containing:

- `free -h`
- `zramctl --output-all`
- `/proc/pressure/memory`
- `podman stats --no-stream`
- `curl http://127.0.0.1:11435/props`
- `curl http://127.0.0.1:11435/slots`
- selected `/metrics` counters and gauges
- recent `llama-cpp` log lines for checkpoint restore, full re-processing, and
  prompt-cache update cost
- `scripts/aoa-qwen-check --case exact-reply`
- one bounded `scripts/aoa-qwen-bench` packet

The lightweight source-owned packet command is:

```bash
scripts/aoa-llamacpp-pilot snapshot --with-checks
```

It writes runtime-local evidence under:

```text
${AOA_STACK_ROOT}/Logs/runtime-benchmarks/tuning-snapshots/llamacpp-tuning-e0/
```

Promotion criterion: no tuning experiment should be accepted unless it improves
memory or latency without contract regression.

### E1: KV quantization comparison

Run the current reviewed `cpu-safe` overlay against the candidate
`cpu-balanced` overlay:

- control: `llamacpp.intel-285h.cpu-safe.yml` with `q8_0 / q8_0`
- candidate: `llamacpp.intel-285h.cpu-balanced.yml` with `q4_0 / q4_0`

Expected value: largest low-risk memory lever already present in the repo.

Risk: long-context or exact-output quality can move, so this needs the Qwen
contract check and a small benchmark packet before any live promotion.

### E2: prompt-cache reuse without 8K jump

The existing `server-cache` overlay jumps to `8192` context while enabling
`cache-reuse=256` and `cache-ram=4096`. That mixes two variables: longer context
and cache behavior.

The cleaner next experiment is a temporary or new candidate overlay with:

- context still `4096`
- `KV_UNIFIED=1`
- `cache-ram=1024`, then `2048`, then `4096`
- `cache-reuse=128`, then `256`
- slots still `1`

Measure:

- whether checkpoint restore frequency improves
- whether the hybrid/SWA full re-processing warning drops
- prompt throughput and generation throughput
- RSS, zram DATA/COMPR/MEM-USED, and memory PSI
- exact-reply and one normal task response

If full re-processing remains frequent, increasing cache RAM is not a real fix.

### E3: idle sleep canary

Because the current `llama-server` supports `--sleep-idle-seconds`, test it on
a pilot lane before touching the canonical module.

Canary shape:

- add the flag through an explicit command/entrypoint path, not assumed env
- start with `600` seconds
- verify wake latency through `aoa-qwen-check`
- verify no broken readiness loop in `langchain-api`
- verify RSS/zram effect after idle and after the first wake request

Do not use this as a replacement for lifecycle orchestration. It is a residency
knob, not a progress-preserving restart mechanism.

### E4: slot save/restore restart route

The server docs describe slot cache save/restore under `/slots/{id}?action=save`
and `/slots/{id}?action=restore` when `--slot-save-path` is configured.

This is worth a pilot because it maps to the operator goal: restart or rotate a
resident model without a full reboot when the lane accumulates stale working
set.

Risk: slot KV cache is not general task state and may be unsafe for some hybrid
memory cases. Treat it as a measured restart optimization, not durable user
progress storage.

### E5: OVMS Intel text challenger

Use the existing `intel-text.ovms-gpu-lab.yml` plus
`intel-text.ovms-qwen3-settings.yml` harness for a separate text-generation
candidate.

Measure it against the canonical lane with:

- exact-reply check
- bounded Qwen benchmark
- RSS and zram delta
- prompt/generation latency
- parser behavior for Qwen reasoning/tool settings

Do not merge this into the default local-worker path without a reviewed packet.

### E6: zram policy only after model lanes

Only after E1-E4 show the real working-set shape, test zram policy:

- compare `lzo-rle` against a zstd-backed generator configuration at boot or in
  a safe downtime window
- inspect whether recompression/writeback features are practically available
  and worth using on this kernel
- if writeback is considered, require an SSD wear budget and explicit backing
  device design
- use `MemoryHigh=` or `MemorySwapMax=` only on optional/background units with a
  known failure boundary

Do not solve a model-cache problem by merely inflating zram. More compressed
swap can hide symptoms while making wake latency and swap churn worse.

## Recommended Next Move

Implement E0 as a small source-owned capture script or pilot subcommand, then
run E1 and E2 as measured packets.

The best immediate tuning hypothesis is:

1. `q4_0 / q4_0` KV can reduce active memory with acceptable quality for the
   local workhorse lane.
2. prompt-cache reuse should be tested at `4096` context before any `8192`
   context experiment.
3. cache RAM should probably shrink from the current `8192 MiB` default unless
   the measured cache hit rate proves it earns its memory.
4. sleep-idle and slot save/restore are promising, but they need pilot wiring
   before live module changes.

## Sources

- llama.cpp HTTP server README:
  <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- Qwen3.5 9B Hugging Face model card:
  <https://huggingface.co/Qwen/Qwen3.5-9B>
- llama.cpp Qwen3.5 full prompt re-processing issue:
  <https://github.com/ggml-org/llama.cpp/issues/20225>
- llama.cpp prompt-cache state drift issue:
  <https://github.com/ggml-org/llama.cpp/issues/21681>
- OpenVINO Model Server continuous batching LLM docs:
  <https://docs.openvino.ai/2026/model-server/ovms_demos_continuous_batching.html>
- OpenVINO Model Server parameters:
  <https://docs.openvino.ai/2026/model-server/ovms_docs_parameters.html>
- OpenVINO Model Server client APIs:
  <https://docs.openvino.ai/2026/model-server/ovms_docs_server_app.html>
- Linux kernel zram documentation:
  <https://www.kernel.org/doc/html/latest/admin-guide/blockdev/zram.html>
- systemd resource-control manual:
  <https://www.freedesktop.org/software/systemd/man/253/systemd.resource-control.html>
