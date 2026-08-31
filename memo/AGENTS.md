# AGENTS.md

## Applies to

This card applies to `memo/`.

## Role

`memo/` is the abyss-stack local memory port. It holds runtime-side memory
candidates, receipts, exports, and local notes before any reviewed landing in
`aoa-memo`.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.
## Boundaries

Write locally as `write_candidate_only` unless a stronger reviewed route is
named by `aoa-memo`.

Use `PORT.yaml` for the local port contract and `INDEX.md` / `index.min.json`
as generated read models. Use `candidates/` for proposed memory, `receipts/`
for review or handoff traces, `exports/` for packets meant for `aoa-memo`, and
`local/` for stack-local notes.

## Candidate Route

Create candidates through the MCP helper from the `abyss-stack` repo root:

Validation is on-demand: use [VALIDATION.md](../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

Then validate the emitted candidate path:


## Reviewed Landing Route

Use this route when a local export is meant to become reviewed `aoa-memo`
memory:


`landing-plan` is still an access-plane check. The durable write happens in
`aoa-memo` through `scripts/memory/land_reviewed_memo_intake.py`, generated
read-model refresh, validators, and review.

## Validation


## Closeout

Report candidate path, evidence refs, validation result, and whether the item
stayed local, was exported for reviewed intake, or was landed in `aoa-memo`.
