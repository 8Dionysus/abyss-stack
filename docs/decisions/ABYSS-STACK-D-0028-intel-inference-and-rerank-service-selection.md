# Intel Inference And Rerank Service Selection

- Decision ID: ABYSS-STACK-D-0028
- Status: accepted
- Date: 2026-05-15
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-15
- Surface classes: runtime profile, machine evidence
- Stack lanes: service selection, inference pilots
- Mechanic parents: inference-pilots, machine-fit
- Guard families: service selection, host evidence freshness
- Posture: accepted service selection rationale

## Context

The Intel workstation stack needed a clearer current service route. Several
live services were useful, but not all screenshot-visible services belonged in
the minimum resident runtime. The machine also had separate host-proven lanes
for Gemma 4 E2B text generation, OpenVINO embeddings, Qwen3 reranking, warm TTS,
and dictation. Future agents needed a durable route that avoids repeating the
same OVMS, llama.cpp, reranker, and TTS debates.

## Options considered

1. Keep using broad presets and leave service selection to live operator memory.
2. Move Gemma 4 E2B into OVMS together with embeddings.
3. Treat the Qwen3 reranker as an OVMS `/v3/rerank` drop-in.
4. Collapse host TTS and stack `qwen-tts` into one resident service.
5. Keep a lean explicit Intel route: Gemma 4 E2B through `llama.cpp` Vulkan,
   embeddings through OVMS, reranking through a dedicated OpenVINO wrapper,
   host TTS and dictation protected, and optional tools, workflows, and
   observability behind explicit profiles or tuning overlays.

## Decision

Use explicit service selection for the Intel route.

`intel-worker` keeps OVMS as the embeddings seam. Gemma 4 E2B uses the explicit
`compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml` lane over
`llama.cpp` Vulkan. Qwen3 reranking uses the opt-in `reranking` profile and
`45-rerank-api.yml` wrapper because the current host-proven artifact is a
CausalLM-style OpenVINO reranker rather than a reviewed OVMS rerank model.
The wrapper loads lazily and unloads after an idle window so reranking remains
available without making another multi-GB model permanently resident. Since
the Python/OpenVINO allocator may retain released pages, the wrapper is allowed
to exit after idle unload and let the container restart policy bring back a
clean lightweight API. The atomic module does not impose hard memory or CPU
ceilings. On the reviewed GPU path, OpenVINO device mappings are charged to the
container memory cgroup as shared memory; a `4 GiB` `memory.max` killed the
owner workload while cgroup swap headroom remained. Lazy load plus owner-aware
idle exit is the resource guard for this service. A constrained-host ceiling,
if one is ever justified, belongs in an explicit measured tuning experiment,
not in the normal reranker module.

Host warm TTS and dictation remain protected machine capabilities. The stack
`qwen-tts` helper stays a stack tools service, not the replacement for the host
operator voice route. TTS warmth is preserved by a bounded keep-warm timer that
exercises the existing protected server through `abyss-machine resource launch`.

## Rationale

This route matches the measured host facts and keeps each capability on the
surface where it currently works best. It also keeps the default stack lean:
storage, worker, federation, reranking, tools, workflows, and observability are
visible choices instead of hidden growth inside one preset.

The route avoids unsupported or weakly proven moves:

- Gemma 4 E2B does not need to be forced through OVMS when the working text lane
  is `llama.cpp` Vulkan.
- The current Qwen3 reranker should not be claimed as an OVMS rerank drop-in
  until a compatible sequence-classification artifact is reviewed.
- TTS and dictation should not be restarted, disabled, or replaced as memory
  relief.

## Consequences

- The lean Intel shape is easier to inspect and reproduce.
- Reranking becomes a stack-owned localhost API without changing the embedding
  service.
- An active rerank request may transiently use more than `4 GiB`; admission must
  account for that cold-load demand instead of relying on a kill boundary.
- Helper tools, n8n, and dashboards remain opt-in and can be capped by explicit
  thin-host overlays.
- There are now more explicit profiles and overlays to validate.
- The reranker wrapper remains a bridge until a better OVMS-compatible artifact
  or another reviewed serving route replaces it.

## Source surfaces

- `docs/runtime/SERVICE_SELECTION.md`
- `docs/runtime/SERVICE_CATALOG.md`
- `compose/modules/45-rerank-api.yml`
- `compose/profiles/reranking.txt`
- `compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml`
- `compose/tuning/intel-worker.thin-host.yml`
- `compose/tuning/federation.thin-host.yml`
- `compose/tuning/observability.thin-host.yml`
- `compose/tuning/storage.intel-285h.resource-guard.yml`
- `compose/tuning/tools.thin-host.yml`
- `compose/tuning/workflows.thin-host.yml`
- `systemd/user/abyss-tts-keepwarm.service`
- `systemd/user/abyss-tts-keepwarm.timer`
- `mechanics/machine-fit/parts/inference-tuning/docs/model-cards/gemma4-e2b-gguf-llamacpp.md`
- `mechanics/machine-fit/parts/inference-tuning/docs/model-cards/qwen3-reranker-0.6b-openvino.md`

## Follow-up route

Revisit this decision only after a new measured packet changes one of the
capability routes: a reviewed OVMS-compatible Gemma route, a reviewed
OVMS-compatible Qwen3 reranker artifact, a better stack-native TTS route that
preserves the operator hot path, or repeated live measurements showing a
different resident service split is safer.
