# REPAIR SAFE CLOSEOUT

## Purpose

After a runtime stress event, closeout should show what was reviewed, what was done, what remained deferred, and what stayed blocked.

The closeout receipt is for repair posture, not self-congratulation.

## When to emit one

Emit `repair_safe_closeout_receipt_v1` only after there is a reviewed closeout-worthy action or explicit reviewed no-action decision.

Do not emit one for every degraded signal.

## What it should include

A useful repair-safe closeout receipt includes:

- source degradation receipt refs
- bounded closeout scope
- reviewed action list
- deferred actions
- restart or rollback posture
- an explicit flag that mutation widening remained blocked
- evidence refs for what was checked after repair or no-action review

## Closeout Examples

The bounded closeout examples include:

- `mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.timeout-chaos.example.json`
- `mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.retrieval-outage-honesty.example.json`

Those examples keep closeout bounded to the owner-local runtime lane and do not
authorize broader recovery or verdict logic.

## Relationship to the SDK

A reviewed closeout receipt can later feed `aoa-sdk` closeout manifests.

It should remain owner-local first.

## Path hygiene

If a repair changes source-owned configuration, make that change in the source checkout.
Do not patch `/srv/AbyssOS/abyss-stack` and pretend the system learned.

## Healthy outcome

A healthy runtime closeout can say:

- what degraded
- how it was contained
- what was reviewed
- what was done
- what still needs work
- what evidence supports the current narrower posture
