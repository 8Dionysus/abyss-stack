# 2026-05-13 Live Runtime Cutover And Machine Parity

## Status

Accepted.

## Context

After the residual quest packet closeout, the next named blocks were not more
quest sorting. They were runtime-loop posture, operational cutover, platform
hardening, source/deployed parity, ignored local cache cleanup, and root-doc
freshness.

Keeping those as prose in `ROADMAP.md` would make future passes repeat the same
argument without a runnable route.

## Decision

Add two package-local runtime-lifecycle packet surfaces:

- `mechanics/runtime-lifecycle/parts/config-sync-boundary/docs/SOURCE_RUNTIME_PARITY_PACKET.md`
- `mechanics/runtime-lifecycle/parts/start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md`

The parity packet may sync repo-managed source surfaces into the deployed
`Configs` mirror, but it does not start services or carry private state. The
cutover packet may inspect live runtime-loop posture, but it does not promote a
seam into live service authority by itself.

## Consequences

- Live runtime cutover now has an executable route instead of a vague roadmap line.
- Machine/runtime connection is checked through source validation, synthetic
  parity, live `Configs` parity, and runtime Configs mirror validation.
- Live service health remains a separate truth from source/deployed parity.
- The current route-api health and closure drift is tracked as
  `ABYSS-STACK-Q-0009` rather than hidden behind green source parity.
- Future runtime-loop promotion should update the relevant packet or open a new
  bounded quest only when a new obligation survives the packet.
