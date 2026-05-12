# USAGE BUDGET POLICY

## Purpose

This document defines the bounded runtime usage and budget posture for `abyss-stack`.

It covers status readout only.
This wave documents status surfaces only.
It does not activate live spend accounting or remote billing semantics.

## Core rule

`abyss-stack` may describe runtime usage pressure.
It must not turn runtime budget posture into proof semantics.
It does not create wallet, payment, or vendor-analysis obligations.

## Vocabulary

- `per-request` means one bounded request envelope
- `session` means one local operator or runtime session window
- `hourly` means one rolling hour posture for the current surface
- `daily` means one rolling day posture for the current surface
- `graceful degrade` means the runtime narrows optional behavior before it hard stops
- `strict stop` means the runtime refuses a class of work when the active budget rule is exhausted
- `reset window` means the next moment a bounded counter is allowed to refresh
- `baseline cost` means a local normalized estimate for the current window, not a price quote
- `savings` means the local normalized estimate of work avoided or shortened, not a financial claim

## First artifact slice

The first slice is a status artifact, not a billing or proof surface.
It is represented by `runtime_usage_snapshot_v1`.

Recommended local path when this surface exists:

- `${AOA_STACK_ROOT}/Logs/runtime-usage/latest/`

The artifact should make these things explicit:

- request, session, hourly, and daily windows
- `policy_mode`
- `degrade_state`
- `strict_stop`
- `baseline_cost_estimate`
- `savings_estimate`
- `reset_at`

This slice is for operator readout only.
It does not change `aoa-doctor`.
It does not create a remote payment contract.
It does not create an `aoa-evals` evidence contract in this wave.

## Boundary notes

Keep the vocabulary runtime-local and machine-readable:

- baseline and savings values should use normalized local units
- budget posture must not become a hidden quality score
- usage pressure must not be presented as proof of correctness
- the snapshot must stay below route meaning, memo meaning, and eval meaning

## One-line rule

`abyss-stack` may expose a bounded runtime usage snapshot, but it must not turn local budget posture into wallet semantics, proof semantics, or quality theater.
