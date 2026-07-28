# Codex Consumer Handoff Remains Owner-Composed

- Decision ID: ABYSS-STACK-D-0097
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/services/abyss-stack-mcp/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP consumer integration, runtime evidence, Codex plane
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: owner boundary, receipt binding, consumer zero, deny by default
- Posture: accepted pre-final consumer handoff

## Context

`abyss-stack-mcp` already models the full runtime observation chain through
registry, consumer schema, proof, acceptance, canary, and rollback. The
source-owned Codex organ-fabric projection belongs in `8Dionysus`, the private
registry belongs in `aoa-sdk`, organ acceptance belongs to each organ owner,
and live configuration plus credentials belong to the operator.

Without an explicit handoff, the stack could accidentally become the hidden
consumer registrar merely because it starts services and can observe
endpoints. Conversely, the consumer projection could treat a stack canary as
registry admission or owner acceptance.

## Options considered

1. Let stack service start automatically register and reload Codex.
2. Duplicate the entire Codex consumer manifest inside `abyss-stack`.
3. Keep the existing typed runtime observation as the machine-readable
   handoff, document field-to-receipt ownership, and require reviewed
   composition across `aoa-sdk`, `abyss-stack`, `8Dionysus`, organ owner, and
   operator.

Options 1 and 2 collapse runtime presence into consumer authority and create
competing source truth. Choose option 3.

## Decision

`abyss-stack` issues stack-local package, deploy, process, endpoint, canary,
policy, and rollback-target evidence. It may carry exact registry,
consumer-schema, proof, and owner-acceptance references, but it cannot
self-issue those facts.

The runtime observation is the stack handoff surface. The Codex consumer
manifest is not duplicated here. `abyss-stack-mcp` has no config apply,
credential read, Codex reload, registration removal, or consumer-zero
inference path.

A live consumer change requires a fresh Codex process unless an exact
client-version reload receipt proves otherwise, followed by schema
re-observation and grounded canaries. A suspended registry record is removed
from Codex only by the operator after consumer-zero and rollback evidence; a
stopped endpoint is not removal proof.

## Rationale

The existing runtime observation already expresses the complete evidence chain
without claiming that every link has the same issuer. Reusing it preserves one
typed runtime truth while the consumer manifest remains independently
reviewable and deny-by-default. Explicit composition makes contradictory or
stale refs fail visibly instead of hiding them behind service health.

## Consequences

- runtime and consumer owners can evolve independently without two manifests;
- every admission fact retains its issuing authority;
- a running server cannot silently activate itself in Codex;
- a consumer entry cannot claim live readiness from source render alone;
- suspension remains fail-closed without destroying compatibility early;
- final integrated landing must join exact refs rather than copy booleans.

## Claim limits

This decision and its source validator prove the handoff boundary only. They
do not prove a live process, endpoint, credential, registration, schema
observation, grounded call, owner acceptance, consumer-zero, or rollback.

## Source surfaces

- `mcp/services/abyss-stack-mcp/docs/CODEX_CONSUMER_HANDOFF.md`
- `mcp/services/abyss-stack-mcp/schemas/runtime-observation.schema.json`
- `mcp/services/abyss-stack-mcp/examples/runtime-observation.public.example.json`
- `mcp/services/abyss-stack-mcp/scripts/validate_stack_mcp.py`

## Follow-up route

At the final landing, populate exact cross-owner receipt refs only after their
issuing repositories land and the operator-approved rollout produces fresh
consumer evidence. Retain all incomplete organs as shadow or suspended.
