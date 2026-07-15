# gemma4-e2b-gguf-llamacpp

- `card_id`: `mc.gemma4-e2b-gguf-llamacpp`
- `scope`: text-only `Gemma 4 E2B` GGUF lane on `langchain-api -> llama.cpp`
- `status`: `candidate`
- `profile_class`: `spark`

## Best For

- bounded local structure checks and compact job summaries
- low-cost resident or near-resident task lanes with one active slot
- Intel-aware stack runs that keep text generation on `llama.cpp` and retrieval embeddings on OVMS
- host-machine jobs where a smaller Gemma 4 lane is preferable to a heavier workhorse lane

## Avoid For

- OVMS or OpenVINO Model Server text-generation promotion
- multimodal claims in the current stack route
- multi-slot resident serving
- replacing the reviewed `workhorse` lane without a fresh promotion packet

## Preferred Backends

- `llama.cpp` Vulkan on the Intel iGPU
- `llama.cpp` CPU fallback only after a bounded comparison

## Validated Lanes

- stack serving lane: `intel-federation` plus
  `compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml`
- host evidence lane: `abyss-gemma4-spark` monitor/digest/micro/jobs timers
  consuming `http://127.0.0.1:11435`

## Candidate Lanes

- `compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml`
- optional owner-admitted cold-load layer:
  `compose/tuning/llamacpp.gemma4-e2b.llama-swap.yml`

## Contract Notes

- this card records a stack route for the host-proven Gemma 4 E2B resident candidate; it does not make the model the default worker for every preset
- serving ownership is stack-first for this lane; do not run the legacy
  host-local `abyss-gemma4-spark.service` beside the stack `llama-cpp`
  container unless explicitly rolling back
- the candidate overlay is text-only and intentionally does not mount an `mmproj`
- keep `-np`/parallelism at one until swap and slot persistence are orchestrated
- keep OVMS on embeddings in `intel-worker`; do not route this model through OVMS as the current stack promotion path
- keep native `--sleep-idle-seconds 600` enabled; health, props, and model
  metadata probes must remain non-waking, while a real inference request owns
  the measured cold return
- use the `llama-swap` overlay only as an explicit candidate after the native
  Vulkan overlay. Its proxy remains resident while the model process is cold,
  admits the measured 2560 MiB load through the private owner socket, and
  returns to cold after 600 idle seconds. Removing that overlay is the rollback
  to native sleep
- the proxy classifies this interactive serving capability as `foreground`;
  timer and batch owners must pass their own resource gate before requesting
  it. This does not authorize a background caller to relabel itself
- prefer the existing f16 KV cache posture until a Gemma 4-specific KV quantization packet proves quality and stability
- use the host cache path through `AOA_GEMMA4_E2B_MODEL_HOST_PATH`; the model file itself is not source-managed
- disable `LC_OPENAI_LITERAL_COMPLETIONS` for this lane; `llama.cpp`
  completions returned empty text for the Gemma 4 chat-template smoke while
  the chat-completions path passed exact-reply and normal `/run` checks

## Evidence Surfaces

- local host trial: `/var/lib/abyss-machine/ai/llm/evals/2026/05/2026-05-14-gemma4-e2b-resident-live-trial.md`
- local host tuning matrix: `/var/lib/abyss-machine/ai/llm/evals/2026/05/2026-05-15-gemma4-e2b-llamacpp-tuning-matrix.md`
- live stack activation packet: `/var/lib/abyss-machine/changes/active/stack-gemma4-e2b-live-activation-20260515/`
- [compose tuning README](../../../../../../compose/tuning/README.md)
- [MODEL_PROFILES](../MODEL_PROFILES.md)

## Next Tests

Run a longer mixed workload before promoting this from candidate to default:
structured JSON, retrieval-assisted `/run/federated`, memory/zram drift over
hours, and a rollback rehearsal to the previous Qwen lane. Promotion requires
that packet plus the normal `intel-federation` smoke suite.
