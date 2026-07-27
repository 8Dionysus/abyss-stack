# Cross-Organ Orchestration Host Boundary

- Decision ID: ABYSS-STACK-D-0095
- Status: accepted
- Date: 2026-07-26
- Owner surface: `abyss-stack` host integration and `abyss-stack-mcp`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, cross-organ orchestration, host receipt chain
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: owner boundary, host-visible receipt, no semantic proxy, rollback
- Posture: accepted host-integration target

## Context

OS Abyss needs to compose direct owner access planes without turning one MCP
server into an authority merger. The first required chain is:

```text
KAG evidence
  -> memo candidate
  -> eval request
  -> eval result
  -> owner acceptance or rejection
```

Current owner contracts already define the bounded artifacts for their own
stages. `aoa-kag` owns evidence and retrieval provenance, `aoa-memo` owns
candidate and reviewed landing meaning, and `aoa-evals` owns eval pressure and
verdict meaning. None owns the whole workflow.

An unlanded `aoa-sdk` source candidate, decision `AOA-SDK-D-0080`, now defines
a strict five-stage state machine. It pins exact owner schema digests and
source revisions, accepts one host-receipted observation at a time, binds each
transition to the previous content-addressed snapshot, and reconstructs the
full chain during validation. It explicitly executes no MCP tool, computes no
proof, writes no durable memory, infers no acceptance, and authorizes no
runtime work.

`abyss-stack-mcp` is the proposed operational access plane for the stack
itself. Its active contract is nevertheless an evidence and candidate plane,
not a semantic proxy, universal bus, or workflow engine. The host integration
must preserve that boundary.

## Options considered

1. Let `aoa-kag-mcp`, `aoa-memo-mcp`, or `aoa-evals-mcp` invoke the other
   servers internally.
2. Add a universal owner-tool proxy to `abyss-stack-mcp`.
3. Let the stack host persist and expose the SDK receipt chain while every
   owner call remains a separate, visible direct-owner action.

## Decision

Choose option 3.

The target host integration uses the `aoa-sdk` state machine as the only
cross-stage contract. `abyss-stack` owns:

- exact run persistence and lifecycle;
- transport and direct-owner endpoint selection;
- credential contour selection without credential copying into a run;
- timeout, cancellation, retry, and idempotency posture;
- issuance of one host-visible receipt per stage;
- operator-visible stop, denial, and rollback routing;
- consumer-facing observation of the current stage and next owner.

`abyss-stack-mcp` may later expose bounded read inspection of orchestration
runs and candidate-only handoff preparation. It must not invoke owner tools,
accept a source or memory change, compute an eval verdict, promote a memo
candidate, or hide a server-to-server chain. Any future MCP write surface
requires its own effect, approval, persistence, replay, concurrency, threat,
and rollback contract before implementation.

The host or explicit playbook calls each direct owner independently. It then
submits the typed owner result and host receipt to the SDK transition. The
resulting next snapshot is persisted before the next owner is called.

The workspace MCP remains discovery-only. It does not expose this
orchestration state machine.

## Rationale

The SDK contract makes cross-object invariants deterministic, while the stack
is the narrow owner for host lifecycle and operational receipts. Keeping owner
calls outside `abyss-stack-mcp` prevents the stack access plane from acquiring
KAG, memory, or proof meaning and makes credentials, failure, retry, and
partial progress visible.

This also permits an operator to connect to stack state through
`abyss-stack-mcp` without using it as a mega-gateway to every organ.

## Consequences

- Hidden KAG-to-memory writes and automatic candidate promotion remain
  forbidden.
- A valid eval result cannot imply memo-owner acceptance.
- Schema, source, freshness, receipt, or previous-snapshot drift stops the
  chain.
- Host persistence and any stack-MCP run inspection are not implemented by
  this decision.
- The current SDK source candidate must land, package, and pass exact
  stack-consumer compatibility before implementation.
- Live owner calls, accepted memory, benefit, cancellation recovery, restart
  replay, and rollback remain separate runtime evidence.

## Claim limits

This decision accepts the host boundary and implementation target. It does not
prove a landed SDK package, stack integration, deployed process, MCP tool
surface, registered consumer, owner invocation, terminal acceptance, measured
benefit, replay recovery, or rollback.

## Source surfaces

- `mcp/services/abyss-stack-mcp/DESIGN.md`
- `mcp/services/abyss-stack-mcp/docs/BOUNDARIES.md`
- `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
- `docs/decisions/ABYSS-STACK-D-0094-wave6-access-form-and-retirement-classification.md`
- `aoa-sdk` source candidate `AOA-SDK-D-0080`
- current `aoa-kag`, `aoa-memo`, and `aoa-evals` owner contracts cited by
  `AOA-SDK-D-0080`

## Follow-up route

Land and package the SDK contract first. Then define the stack persistence,
read inspection, candidate handoff, cancellation, restart replay, concurrency,
and rollback contract before adding any `abyss-stack-mcp` surface. Validate
exact SDK schema and package compatibility and keep owner invocation outside
the stack MCP server.
