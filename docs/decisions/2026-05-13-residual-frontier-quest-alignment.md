# 2026-05-13 Residual Frontier Quest Alignment

Status: accepted
Date: 2026-05-13

## Context

After the mechanics package-card refactor, the remaining repo-level work was no
longer a flat topology cleanup. The open questbook still listed several
obligations as `captured` even though some source contracts had already landed
and other items had a clear next operator packet.

Leaving everything as `captured` made the frontier look less mature than the
source tree. Closing everything without packet evidence would have been worse:
source-ready contracts alone do not prove runtime materialization, private
machine state, or operator cutover.

## Options considered

1. Keep all residual quest records in `captured` until live runtime proof exists.
2. Close every residual quest from source prose alone.
3. Classify each residual quest by the strongest evidence the source checkout or packet can prove.

## Decision

Classify residual quests by what the source checkout can honestly prove, then
move each quest only after its corresponding packet is executed:

- use `done` only when the source-side contract or source slice is landed,
  public-safe, and validator-covered without requiring live runtime state, or
  when a bounded synthetic/runtime packet was executed and verified
- use `ready` when the owner route is shaped and the next action is a bounded
  runtime or operator packet
- keep `QUESTBOOK.md` as the active public index, not a history list for closed
  quest IDs
- keep closed quest records under their lane-local `done/` state for audit
  without listing them as current obligations

The resulting packet closeout is:

- profile rollout: done through
  `mechanics/machine-fit/parts/fit-record/docs/PROFILE_MACHINE_FIT_PACKET.md`
- machine fit: done through
  `mechanics/machine-fit/parts/platform-adaptations/docs/MACHINE_FIT_FOLLOW_THROUGH_PACKET.md`
- RPG service contracts: done as source contracts
- RPG runtime collections: done through
  `mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_MATERIALIZATION_PACKET.md`
- diagnostic spine: done through
  `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_RUNTIME_PACKET.md`
- ToS graph curation: done as a localhost-only source slice

## Rationale

A quest state should reflect what the repository can prove. Source-side contracts, executed packets, and live runtime health are different evidence classes, so the quest frontier needs to move by evidence rather than by optimism or inertia.

## Consequences

The source checkout now separates three things that previously blended together:

- already-landed source contracts
- executed source/runtime packets
- future live runtime cutover

This does not mutate live `/srv/AbyssOS/abyss-stack` state, does not claim that
the live deployed runtime is green, and does not promote sibling-owned AoA or
ToS meaning into `abyss-stack`.

Future changes that need more work should open a new bounded quest only when a
new obligation survives this closeout. Repeated packet reruns should update the
owning packet docs or landing logs instead of reintroducing active root quest
noise.

## Source surfaces

- `QUESTBOOK.md`
- `quests/`
- `mechanics/machine-fit/parts/fit-record/docs/PROFILE_MACHINE_FIT_PACKET.md`
- `mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_MATERIALIZATION_PACKET.md`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_RUNTIME_PACKET.md`

## Follow-up route

Open a new bounded quest only when a new obligation survives the packet route; otherwise update the owning packet or landing log.
