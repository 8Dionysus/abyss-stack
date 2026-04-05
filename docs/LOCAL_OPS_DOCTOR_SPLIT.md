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
- the current exit semantics documented in `docs/DOCTOR.md`

## Future local ops readout owns

The future local ops layer is only documented in this wave as a bounded local ops status surface.

Its checklist should stay narrow:

- gateway reachability
- log presence
- basic config health
- local floor availability

That future readout may summarize runtime-local status after startup.
It does not replace `aoa-doctor`.
It does not absorb `aoa-host-facts` or `aoa-machine-fit`.

## What this wave does not do

This wave does not add new `aoa-doctor` exit semantics.
This wave does not add operator UI.
This wave does not add usage accounting to `aoa-doctor`.

## One-line rule

Keep readiness in `aoa-doctor`, keep post-start local status in a separate bounded surface, and do not merge them into one vague operations blob.
