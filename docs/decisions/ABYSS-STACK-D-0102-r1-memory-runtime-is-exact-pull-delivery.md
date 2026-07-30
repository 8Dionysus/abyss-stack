# R1 Memory Runtime Is Exact Pull Delivery

- Decision ID: ABYSS-STACK-D-0102
- Status: accepted
- Date: 2026-07-29
- Owner surface: `mechanics/federation-seams/parts/memo-seam/`

## Index Metadata

- Original date: 2026-07-29
- Surface classes: runtime contract, federation seam
- Stack lanes: runtime, source, MCP
- Mechanic parents: federation-seams
- Guard families: owner boundary, exact delivery, no hidden persistence
- Posture: accepted reduced-organ rationale, unlanded

## Context

The memo seam now validates explicit-pull, shadow, canary, agent-local, and
erasure receipts. Runtime capability must not make all those contours active
or let delivery reinterpret the memory plan.

## Options considered

- Enable shadow/canary delivery whenever the schemas validate.
- Let the stack rerank and persist useful memo packets.
- Admit only exact explicit-pull delivery in R1 and retain wider seams as
  disabled contracts.
- Move memo meaning into the stack store.

## Decision

R1 admits only exact read-only delivery for the explicit-pull A consumer.

`abyss-stack` validates the SDK plan, memo bundle, host refs, policy/version,
expiry, and content digests; delivers only the selected items; and emits a
content-minimized C20 receipt. It does not rerank, reselect, expand, persist,
promote, execute, or reinterpret memory.

Shadow/canary and agent-local runtime seams remain disabled source contracts
without a live trigger, default consumer, service, private store, or
promotion/effect route. MCP remains an access plane only.

## Rationale

Exact delivery gives the runtime a useful bounded role without absorbing
semantic, policy, proof, routing, or host authority. Disabled wider seams keep
future compatibility testable while preventing implementation presence from
becoming activation.

## Consequences

- A delivery has an exact no-memory rollback.
- Runtime failure cannot silently switch to a stronger memory mode.
- Consumer-zero must be proven for every excluded seam before landing.
- Live private storage needs a separate stack decision and erase proof.

## Source surfaces

- `mechanics/federation-seams/parts/memo-seam/`
- `docs/BOUNDARIES.md`
- `docs/decisions/ABYSS-STACK-D-0097-codex-consumer-handoff-remains-owner-composed.md`
- `docs/decisions/ABYSS-STACK-D-0101-retire-routing-predecessor-checkout-consumers.md`

## Follow-up route

Run the memo-seam and full stack validators, then keep runtime activation
absent until the consolidated landing and a separate operator-visible enable
step.
