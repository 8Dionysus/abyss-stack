# MODEL PROFILES

## Purpose

This document defines class-based model profiles for `abyss-stack`.

It does not name one true vendor or one permanent model brand.
It defines the infra-facing profile classes the stack should be able to host.

## Core rule

`abyss-stack` owns runtime profile posture, not agent-layer tier meaning.

The stack should answer:

- what class of model is being hosted
- what latency and memory posture it implies
- what context budget posture it expects
- where the profile belongs in local storage and serving policy

## Profile classes

### `spark`

Use for:

- fast routing
- quick structure checks
- lightweight archive or summary passes

Expected posture:

- lowest latency budget
- smallest VRAM and RAM expectation
- short working context

### `workhorse`

Use for:

- ordinary planning and execution
- default bounded task work
- most multi-step local routes

Expected posture:

- moderate latency budget
- moderate context budget
- best balance for steady local operation

### `deep`

Use for:

- synthesis
- contradiction arbitration
- expensive reasoning passes
- rare high-cost judgment

Expected posture:

- highest latency budget
- strongest resource requirement
- should be invoked selectively rather than by default

### `archive`

Use for:

- distillation
- summary packs
- entity and decision extraction
- writeback preparation

Expected posture:

- optimized for structured output and compression fidelity
- does not need to be the deepest model
- may prefer throughput stability over depth

## Profile fields the stack should preserve

Each runtime profile should be able to name:

- `profile_class`
- `latency_budget`
- `context_budget_class`
- `storage_tier`
- `serving_path`
- `quantization_or_runtime_variant`

## Storage posture

The stack should keep heavier profiles explicit about storage placement.

Preferred rule:

- fast and frequently used assets stay on the active runtime root when practical
- colder and heavier assets may live on the mounted heavy-data tier when available
- path policy must remain explicit so `/abyss` absence does not silently spill onto the system disk

## Boundaries to preserve

- do not publish model brands as doctrine
- do not encode human role meaning here
- do not turn runtime profiles into routing truth
- do not treat one quantization as permanent canon

Return posture should also remain class-based.
`spark` should use the thinnest anchor-only rebuild, `workhorse` should be the default checkpoint-first return class, `deep` may allow richer selective recall, and `archive` should stay summary-first rather than becoming generic continuation.
