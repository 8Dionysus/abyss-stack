# RUNTIME WINNER PROMOTION LOOP

## Purpose

This document defines the reviewed operator loop for promoting a runtime
challenger into the current live winner on `abyss-stack`.

Use it when:

- a `llama.cpp` pilot packet looks strong enough to challenge the live lane
- an explicit Intel-served text lane survives its bounded packet and needs a
  promotion decision
- a stale fallback overlay or old machine-fit posture must be retired
- a kernel, driver, or container-runtime change means the old winner must be
  re-checked before trusting it again

It does not replace:

- `RUNTIME_BENCH_POLICY`, which owns benchmark evidence
- `MACHINE_FIT_POLICY`, which owns the current host posture
- `PLATFORM_ADAPTATION_POLICY`, which owns bounded seam-bending records
- `MODEL_CARDS`, which own family and variant fit notes

## Core rule

Do not promote from:

- one flattering packet
- one model card
- one host anecdote
- one fallback overlay that happened to keep the stack alive

Promote only through a reviewed loop that keeps:

- machine-fit fresh
- current winner explicit
- challenger packet bounded
- adaptation record visible
- live re-check separate from the challenger run

## When to run this loop

Run the loop when one of these is true:

- the current live winner is stale because kernel, driver, runtime image, or
  package freshness changed materially
- a challenger packet survives with better bounded posture than the current
  winner
- the live runtime is still honoring a fallback overlay that should be retired
- a model-card or Intel-serving lane is ready to move from `candidate` toward a
  reviewed runtime decision

Do not run this loop when:

- you only need exploratory lab packets
- the challenger failed its bounded contract packet
- the question is proof-layer meaning rather than runtime posture

## Inputs

- current live winner or fallback posture
- current private machine-fit record
- latest platform-adaptation record when one exists
- one bounded challenger packet
- current smoke or verify surface for the live lane

## The loop

### 1. Re-read the current winner

Start by making the current live winner explicit:

- read the latest machine-fit record
- read the latest platform-adaptation record
- inspect whether a fallback overlay is still being auto-applied
- identify the current live runtime path and current promoted packet basis

If that read is already unclear, stop and clarify the current winner before
running more packets.

### 2. Refresh machine-fit when the host drifted

If kernel, drivers, package freshness, or runtime images changed materially:

```bash
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

Do not compare a new challenger against a stale host posture if the machine
itself materially changed underneath the runtime.

### 3. Keep the challenger bounded

Run exactly one bounded challenger path.

For `llama.cpp`, prefer:

```bash
scripts/aoa-llamacpp-pilot run --preset intel-full --overlay <candidate-overlay>
```

For explicit Intel-served text challengers, use the isolated sidecar lane and
its bounded contract packet rather than rewriting the canonical live profile.

### 4. Read contract-fit before speed

Compare in this order:

1. did the challenger stay on its bounded contract surface?
2. did it remain stable and reviewable?
3. only then read latency or throughput as a promotion input

If the challenger is faster but weaker on contract-fit, it is not the winner.

### 5. Record the adaptation

When the challenger genuinely beats the current winner on the bounded posture
that matters, write or refresh the platform-adaptation record and make the new
overlay or selection explicit.

This is where stale fallback posture should be retired and replaced with an
explicit reviewed adaptation or reviewed machine-fit winner.

### 6. Repoint the live runtime

Only after the reviewed decision:

- update the bounded overlay or selection surface
- sync configs if needed
- refresh the deployed runtime

The live runtime update is a separate step from the challenger packet itself.

### 7. Re-check the live lane

After the live runtime is repointed, re-run the canonical live checks:

```bash
scripts/aoa-doctor --preset intel-full
scripts/aoa-up --preset intel-full
scripts/aoa-wait --preset intel-full
scripts/aoa-smoke --with-internal --preset intel-full
scripts/aoa-qwen-bench --profile intel-worker
```

Or use the narrower live-path verify flow when that is the current reviewed
surface.

The winner is not really promoted until the live lane itself passes.

## Expected outputs

A strong promotion pass leaves:

- one explicit current winner
- one fresh machine-fit read when needed
- one bounded challenger packet
- one visible adaptation decision
- one live re-check on the promoted path

## Current host example

On the current Intel Core Ultra 9 285H reference host, the reviewed live winner
after the `llama.cpp` tuning-argument seam repair remains the
`compose/tuning/llamacpp.intel-285h.cpu-safe.yml` tuning packet, but hosts that
do not expose `avx512f` should keep
`compose/tuning/llamacpp.runtime-fallback.yml` in front of that winner until
the active `server-openvino` seam survives a live re-check without `SIGILL`.

That winner replaced an older fallback overlay only after:

- a fresh machine-fit read
- bounded challenger packets
- a reviewed platform-adaptation update
- and a live `aoa-smoke` plus `aoa-qwen-bench` re-check

`vulkan-lab` remains a working lab seam on that host, but it is not the winner
because it did not beat the bounded contract-plus-latency read of the current
CPU-safe path.

## Skill exposure posture

The stack-owned diagnostic procedure is canonical at:

- `skills/abyss-self-diagnostic-spine`

It is exposed once through the OS user profile and is not duplicated under
`.agents/skills`. The remaining shared `abyss-*` procedures stay in the
transitional `.agents/skills` projection until their owner homes and global OS
replacements have been admitted and manually proven. Repository validation
keeps both boundaries visible.

## Boundary to preserve

`abyss-stack` may decide which runtime path currently wins on one host through a
reviewed operator loop.

It does not turn that winner into proof-layer meaning by itself.
