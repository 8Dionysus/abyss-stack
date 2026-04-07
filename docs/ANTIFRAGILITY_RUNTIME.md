# ANTIFRAGILITY RUNTIME

## Goal

Make runtime stress in `abyss-stack` legible, bounded, and teachable.

When a service or profile degrades, the stack should leave a usable trail instead of a pile of smoke.

## What counts as runtime stress here

Examples include:

- service unavailability
- partial degraded profile activation
- machine-fit mismatch that forces a narrower posture
- mount or storage partial loss
- inference path degradation
- runtime-vs-source path confusion that risks unsafe edits

## Wave-2 contracts

This wave introduces two owner-local receipt families:

- `service_degradation_receipt_v1`
- `repair_safe_closeout_receipt_v1`

Together they should answer:

- what service or profile degraded
- how the damage was contained
- what unsafe repair remained blocked
- what reviewed closeout happened afterward

## Evidence posture

Good evidence sources include:

- `python scripts/validate_stack.py`
- `python scripts/validate_stack.py --parity-check`
- `python /srv/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60`
- `bash /srv/abyss-stack/Configs/scripts/aoa-status --autonomy --json`
- bounded host-facts or machine-fit artifacts when relevant

## Boundary reminder

`~/src/abyss-stack` is the source checkout.
`/srv/abyss-stack` is the deployed runtime mirror.

A runtime stress event must not become an excuse to edit the deployed mirror as if it were the source repository.

## Guardrails

- no hidden auto-repair fan-out
- no blanket restart of unrelated services
- no widening beyond the bounded degraded surface
- no repair story without evidence refs
- no path confusion between source and deployed runtime roots
