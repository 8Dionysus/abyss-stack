# TRUTH SURFACES

## Purpose

This document fixes the language for source, deployment, trial, and live-runtime claims in `abyss-stack`.

Use it whenever a report, summary, or operator note could blur the line between:

- what exists in the canonical source checkout
- what is actually deployed under `/srv/AbyssOS/abyss-stack`
- what a trial packet proved
- what is operator-visible right now

## Canonical statuses

Every promoted runtime claim should be read through these four fields:

- `source_authored`
  The surface exists in the canonical source checkout, usually `~/src/abyss-stack` or the configured `${AOA_SOURCE_ROOT}`.
- `deployed`
  The same operator-facing surface exists in the deployed runtime tree at `/srv/AbyssOS/abyss-stack`, usually under `/srv/AbyssOS/abyss-stack/Configs/`.
- `trial_proven`
  A bounded trial packet recorded a passing result for the claim under the relevant runner contract.
- `live_available`
  The surface is confirmed through a deployed path or live endpoint, not merely by inspecting source files.

## Required interpretation

trial_proven is not a synonym for production readiness.

- A source-authored change is not live just because it landed in the checkout.
- A deployed surface is not trial-proven just because it exists under `/srv/AbyssOS/abyss-stack`.
- `trial_proven` is not a synonym for production readiness.
- `trial_proven` is not a synonym for `live_available`.
- `live_available` must be proved through the deployed operator path or a live endpoint, not by calling source-only helpers.

## Current motivating example

The bounded-autonomy drift pattern made this distinction operationally important:

- `aoa-llamacpp-pilot verify` existed in source before it existed in the deployed `Configs/scripts` copy
- `aoa-sync-federation-surfaces --check --json` existed in source before it existed in the deployed `Configs/scripts` copy

That means a claim could be:

- `source_authored = true`
- `deployed = false`
- `trial_proven = true`
- `live_available = false`

This is not a wording nuance. It is a real runtime-boundary distinction.

## Reporting rule

Local trial surfaces should carry `truth_status` in their summaries and wave indexes.

At minimum, reports should let an operator see:

- whether the claim is source-authored
- whether it is deployed
- whether a bounded trial passed
- whether the capability is currently live-available

Note: Governed canary trust evidence is not a fifth truth status and does not widen execution permissions by itself.

## Historical backfill rule

Older pilot mirrors may predate explicit `truth_status` fields.

When backfilling those reports:

- add a clear correction layer
- do not silently rewrite history as if the distinction always existed
- preserve the original pass/fail record while clarifying the current truth state

## Operator check

Use these steps before promoting a runtime-control claim:

```bash
python scripts/validate_stack.py --parity-check
python /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60
bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-sync-federation-surfaces --check --json --layer aoa-routing
scripts/aoa-status --autonomy --json
```
