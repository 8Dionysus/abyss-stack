# AGENTS.md

## Applies to

This card applies to `mechanics/federation-seams/parts/memo-seam/`.

## Role

This part owns the runtime seam for bounded `aoa-memo` federation: public-safe
mirror refresh, read-only route-api inspection, and runtime candidate export.
Memo meaning stays in `aoa-memo`; this part owns only the stack-side adapter
route.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Runtime Routes

Refresh the public-safe memo mirror through the focused procedure in [VALIDATION.md](../../../../VALIDATION.md).

Inspect the memo seam after the `federation` profile is up:


Emit a bounded memo export candidate:


## Validation

Use the on-demand validation route in `VALIDATION.md` for the exact seam
checks and preserve its live-read, candidate-export, and destructive-action
warnings.

## Closeout

Report whether the work touched mirror refresh, route-api inspection, or
candidate export, whether C20 runtime delivery receipt posture changed, and
state which `aoa-memo` source surfaces were consumed. If ER4/ER5 is in scope,
also report exact runtime versus backup surface coverage, recovery-probe
posture, residue, and whether live deletion remained false.
For Phase 12, report namespace isolation, local rollback/expiry,
consumer-zero, shared-organ availability, and whether live execution remained
false.
