# Live Runtime Cutover And Machine Parity

- Decision ID: ABYSS-STACK-D-0016
- Status: accepted
- Date: 2026-05-13
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-13
- Surface classes: source/runtime boundary, validation guard
- Stack lanes: runtime root, config projection
- Mechanic parents: config-projection
- Guard families: source/runtime boundary, validation lane
- Posture: accepted parity rationale

## Context

After the residual quest packet closeout, the next named blocks were not more
quest sorting. They were runtime-loop posture, operational cutover, platform
hardening, source/deployed parity, ignored local cache cleanup, and root-doc
freshness.

Keeping those as prose in `ROADMAP.md` would make future passes repeat the same
argument without a runnable route.

## Options considered

1. Keep runtime-loop and parity work as prose in root `ROADMAP.md`.
2. Open broad follow-up quests without executable packet surfaces.
3. Add package-local parity and cutover packets with clear non-promotion boundaries.

## Decision

Add two package-local runtime-lifecycle packet surfaces:

- `mechanics/runtime-lifecycle/parts/config-sync-boundary/docs/SOURCE_RUNTIME_PARITY_PACKET.md`
- `mechanics/runtime-lifecycle/parts/start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md`

The parity packet may sync repo-managed source surfaces into the deployed
`Configs` mirror, but it does not start services or carry private state. The
cutover packet may inspect live runtime-loop posture, but it does not promote a
seam into live service authority by itself.

## Rationale

A packet surface gives future operators a repeatable route that is stronger than roadmap prose and narrower than live service promotion. It keeps source parity, deployed mirror parity, and runtime health as separate truths.

## Consequences

- Live runtime cutover now has an executable route instead of a vague roadmap line.
- Machine/runtime connection is checked through source validation, synthetic
  parity, live `Configs` parity, and runtime Configs mirror validation.
- Live service health remains a separate truth from source/deployed parity.
- The first route-api health and closure drift was tracked as
  `ABYSS-STACK-Q-0009` rather than hidden behind green source parity; the
  closed repair keeps the source unit generic and uses a host-local
  runtime-selection drop-in to preserve `intel-full` while layering
  `federation`.
- Future runtime-loop promotion should update the relevant packet or open a new
  bounded quest only when a new obligation survives the packet.

## Source surfaces

- `mechanics/runtime-lifecycle/parts/config-sync-boundary/docs/SOURCE_RUNTIME_PARITY_PACKET.md`
- `mechanics/runtime-lifecycle/parts/start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md`
- `quests/diagnostics/done/ABYSS-STACK-Q-0009.yaml`
- `ROADMAP.md`

## Follow-up route

Rerun or update the runtime-lifecycle packets when source/runtime parity or live runtime-loop promotion pressure changes.
