# MACHINE FIT POLICY

## Purpose

This document defines the bounded machine-fit layer for `abyss-stack`.

The stack is not meant to run as if every host were interchangeable.
It should:
- discover what the current machine can actually do
- prefer the strongest validated runtime path available on that machine
- record driver and package freshness as part of runtime posture
- keep that posture explicit enough for humans and agents to re-check later

## What machine-fit is

`machine-fit` is the current-host answer to:

**what runtime selection, acceleration posture, and validated local tuning should this machine use right now?**

It sits between:
- `REFERENCE_PLATFORM.md`, which says what the stack is shaped for in general
- host facts, which say what this host looks like
- platform-adaptation records, which say what seam bent and what bounded change helped
- runtime benchmarks, which say what latency or behavior was actually measured

## What belongs here

Use this layer for:
- preferred preset or profile selection for the current host
- current driver posture for visible accelerators
- package freshness for the host packages that matter to the runtime path
- validated local runtime settings such as canonical `llama.cpp` serving posture or bounded embeddings posture settings
- bounded compose overlays that should travel with the current host posture
- warnings about noisy host envelopes that can distort latency-sensitive work
- compact refs to host facts, benchmark evidence, and adaptation records

Do not use this layer for:
- secret-bearing config
- general troubleshooting diaries
- broad capability marketing
- proof-layer quality claims
- authored doctrine from sibling AoA repositories

## Relationship to other artifacts

- `aoa-host-facts` records what the machine is
- `aoa-machine-bridge` records the read-only route from the stack runtime to `abyss-machine` evidence and launch gates
- `aoa-machine-fit` records what runtime posture the machine should currently prefer
- `aoa-platform-adaptation` records what specific seam bent and what bounded change helped
- runtime benchmarks record measured behavior on the intended path

The machine-fit layer is the operational bridge between inventory and retestable posture.
When a current private machine-fit record exists, the lifecycle wrappers may auto-apply its validated settings and recommended overlays for the deployed runtime.

## Artifact surfaces

- `mechanics/machine-fit/parts/fit-record/schemas/schema.v1.json` defines the public contract
- `mechanics/machine-fit/parts/fit-record/examples/machine-fit.public.json.example` shows the intended public-safe shape
- `${AOA_STACK_ROOT}/Logs/machine-fit/` is the local capture root

## Capture modes

### `public`

Use when the artifact may live in git or be shared across machines.

It should include:
- hardware class
- kernel release
- visible accelerator posture
- package freshness state
- preferred preset or profile set
- validated public-safe tuning keys
- compact refs to public-safe host facts and reviewed adaptation examples when available

It must not include:
- hostnames
- exact local-only paths
- usernames or home directories unless intentionally public
- secret-bearing env values

### `private`

Use when preserving the local machine record that operators and agents will actually consult.

It may add:
- local refs under `${AOA_STACK_ROOT}/Logs/`
- fuller local driver and device posture
- local benchmark refs
- current host envelope warnings

It still must not capture secrets.

## Storage contract

Recommended active tree:

```text
${AOA_STACK_ROOT}/Logs/machine-fit/
  latest/
    latest.private.json
  records/
    2026-03-29T230000Z__machine-fit__intel-core-ultra-9-285h/
      machine-fit.private.json
```

Rules:
- keep the JSON compact and export-friendly
- reference bulky evidence instead of copying it
- treat the machine-fit record as operational posture, not as benchmark truth
- refresh it when kernel, firmware, drivers, container runtime, or validated local tuning changes

## Strong record checklist

A strong machine-fit record captures:
- the current hardware class
- the visible accelerator and driver posture
- whether relevant host packages are current in configured repos
- the preferred preset or profile set
- the bounded validated runtime settings worth reusing
- any bounded recommended overlays worth auto-applying on that host
- whether the current host envelope is quiet enough for latency-sensitive work
- what to re-test when the machine drifts

## Host-profile rollout note

Machine-fit is where host-profile candidates become legible, not where they become silently promoted.

For the current Intel Core Ultra 9 285H family:
- keep `llama.cpp` as the current reviewed text-serving default
- treat `Gemma 4 E2B/E4B` and `Qwen3.5 4B/9B` as additive host-fit candidate lanes whose promotion depends on measured runtime packets rather than model-card marketing
- treat Vulkan as the first candidate GPU validation lane for additive host-profile work
- treat broader OVMS, OpenVINO, and OpenVINO GenAI serving lanes as additive and separately reviewed rather than as embeddings-only forever or as automatic replacements for `llama.cpp`
- keep SYCL, OpenVINO GPU/NPU, and TurboQuant in explicit benchmark or lab posture until a reviewed promotion decision moves them into validated settings or overlays

The current source-owned candidate overlay family for that host class is:
- `compose/tuning/llamacpp.intel-285h.cpu-safe.yml`
- `compose/tuning/llamacpp.intel-285h.cpu-balanced.yml`
- `compose/tuning/llamacpp.intel-285h.server-cache.yml`
- `compose/tuning/llamacpp.intel-285h.kv-iq4nl-lab.yml`
- `compose/tuning/llamacpp.intel-285h.vulkan-lab.yml`

Use those overlays for bounded runtime packets and pilot work.
Do not auto-promote them into machine-fit `recommended_overlays` until the runtime packet says which lane actually survived on this host.

When a candidate lane looks strong enough to challenge the current live winner,
use [RUNTIME_WINNER_PROMOTION_LOOP](RUNTIME_WINNER_PROMOTION_LOOP.md) instead of
promoting from one packet or one model card by intuition alone.

## Suggested commands

Public-safe review:

```bash
scripts/aoa-machine-fit --mode public --write /tmp/machine-fit.public.review.json
scripts/aoa-machine-bridge --mode public --write /tmp/machine-bridge.public.review.json
```

Local private capture:

```bash
scripts/aoa-machine-bridge --write-latest
scripts/aoa-machine-fit \
  --mode private \
  --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

## Boundary to preserve

`abyss-stack` may own the runtime-local record of what this machine should run and re-check.

It does not own the global meaning of sibling AoA layers, and it does not replace runtime benchmarks or proof artifacts.

A bounded runtime comparison by itself does not change the preferred machine-fit posture.
Only a reviewed promotion decision should move a candidate path into the validated preferred runtime path.

The current reviewed posture is:
- `llama.cpp` as the canonical bounded local-worker path on `5403`
- the current reviewed Intel serving seam in promoted presets routes embeddings through OVMS, while broader OVMS, OpenVINO, and OpenVINO GenAI lanes remain additive and reviewed separately from the canonical `llama.cpp` text path
- the reviewed default keeps full-precision KV cache on the canonical lane, while `q8_0`, `q4_0`, and `iq4_nl` live in explicit Intel 285H candidate overlays until a measured promotion decision says otherwise
- on the current Intel 285H reference host, the latest reviewed packet after the `llama.cpp` tuning-argument seam repair keeps `compose/tuning/llamacpp.intel-285h.cpu-safe.yml` as the tuning winner for the canonical live lane, but machine-fit should still prepend `compose/tuning/llamacpp.runtime-fallback.yml` when the host lacks `avx512f` and the current `server-openvino` seam does not survive live re-check
- `compose/tuning/llamacpp.intel-285h.vulkan-lab.yml` is now a working `server-vulkan` lab seam on that host, but it remains non-promoted until a reviewed packet shows a clear advantage over the current CPU-safe winner
