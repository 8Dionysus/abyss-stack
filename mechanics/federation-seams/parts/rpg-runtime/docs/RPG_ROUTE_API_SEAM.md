# RPG Route API Seam

## Purpose

This note defines the future read-only `/rpg/*` seam for the existing localhost-only `route-api`.

It is not implemented in this source contract.
The seam exists as a bounded contract so the runtime RPG collections can later become inspectable without adding a new authority layer or a new host port.

## Core rule

`/rpg/*` is advisory and read-only.

It reads runtime-owned collection files.
It does not write them.
It does not write upstream repos.

## Backing data

Preferred read order:

1. `${AOA_STACK_ROOT}/Logs/rpg/latest/*.json`
2. source-managed `mechanics/federation-seams/parts/rpg-runtime/generated/*.json` when running in source or dry-run mode

## Raw read surfaces

The first thin raw reads should be:

- `GET /rpg/builds`
- `GET /rpg/reputation`
- `GET /rpg/runs`
- `GET /rpg/projections`

## Structured advisory reads

The first structured reads should stay narrow:

- `POST /rpg/agent-sheet`
- `POST /rpg/quest-board`
- `POST /rpg/campaign-lane`
- `POST /rpg/reputation-panel`
- `POST /rpg/run-inspect`

These endpoints may:
- filter existing collection data
- resolve one card or panel by ref
- keep source refs visible
- preserve canonical keys

These endpoints must not:
- claim quests
- mark quests complete
- award progression
- grant unlocks
- rewrite ledgers
- mutate source state

## Frontend posture

A frontend may later call `/rpg/*`, but the seam remains a data reader, not a gameplay engine.

If a UI wants to trigger action, it still routes through existing owner or orchestrator surfaces.
The card itself is not the command.

## Visibility posture

Keep the seam localhost-only with the existing `route-api` posture.

Do not add:
- a new public port
- a browser-facing write service
- hidden mutation endpoints
- hidden operator shortcuts that bypass review

## Final rule

The seam should read like a lantern, not a wand.
