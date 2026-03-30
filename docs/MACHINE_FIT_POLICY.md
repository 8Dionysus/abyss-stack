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
- validated local runtime settings such as bounded Ollama thread or batch posture
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
- `aoa-machine-fit` records what runtime posture the machine should currently prefer
- `aoa-platform-adaptation` records what specific seam bent and what bounded change helped
- runtime benchmarks record measured behavior on the intended path

The machine-fit layer is the operational bridge between inventory and retestable posture.

## Artifact surfaces

- `docs/machine-fit/schema.v1.json` defines the public contract
- `docs/machine-fit/machine-fit.public.json.example` shows the intended public-safe shape
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
- whether the current host envelope is quiet enough for latency-sensitive work
- what to re-test when the machine drifts

## Suggested commands

Public-safe review:

```bash
scripts/aoa-machine-fit --mode public --write /tmp/machine-fit.public.review.json
```

Local private capture:

```bash
scripts/aoa-machine-fit \
  --mode private \
  --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

## Boundary to preserve

`abyss-stack` may own the runtime-local record of what this machine should run and re-check.

It does not own the global meaning of sibling AoA layers, and it does not replace runtime benchmarks or proof artifacts.

An optional runtime sidecar pilot, such as a bounded `llama.cpp` comparison, does not change the preferred machine-fit posture by itself.
Only a reviewed promotion decision should move a pilot path into the validated preferred runtime path.
