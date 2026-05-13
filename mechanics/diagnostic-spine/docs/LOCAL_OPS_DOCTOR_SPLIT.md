# LOCAL OPS DOCTOR SPLIT

## Purpose

This document preserves the split between `aoa-doctor` and a future local ops status readout.

## Core rule

`aoa-doctor` remains readiness-only.
It answers whether the current host and selected runtime shape are ready enough to start.

It does not become a usage monitor.
It does not become a cache console.
It does not become an operator control plane.

## `aoa-doctor` owns

- pre-start host and runtime readiness
- profile-aware warnings and failures
- bootstrap and layout checks
- the current exit semantics documented in `mechanics/diagnostic-spine/docs/DOCTOR.md`

## Future local ops readout owns

The post-start local ops layer now begins with the bounded local ops status surface exposed through the read-only `aoa-diagnose` seam.

Its checklist should stay narrow:

- gateway reachability
- log presence
- basic config health
- local floor availability
- diagnostic-session normalization for one selected runtime target

That readout may summarize runtime-local status after startup.
It does not replace `aoa-doctor`.
It does not absorb `aoa-host-facts` or `aoa-machine-fit`.
It does not grant repair authority.

## What This Contract Does Not Do

This wave does not add new `aoa-doctor` exit semantics.
This wave does not add operator UI.
This wave does not add usage accounting to `aoa-doctor`.
This wave does not let `aoa-diagnose` mutate runtime, quest, or repair state.

## One-line rule

Keep readiness in `aoa-doctor`, keep post-start local status in a separate bounded surface, and do not merge them into one vague operations blob.
