# Agent OS Subprocess Runtime Adapter

- Decision ID: ABYSS-STACK-D-0098
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mechanics/governed-execution/parts/agent-os-adapter/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: runtime contract, integration, governed execution
- Stack lanes: runtime lane, federation seam, decision lane
- Mechanic parents: governed-execution
- Guard families: explicit adapter, durable lifecycle, approval boundary, no hidden execution
- Posture: accepted rationale

## Context

`aoa-sdk` now owns routing, runtime-neutral plan compilation, and the
`AoARunner` lifecycle client. `abyss-stack` already owns the real governed
execution lane for bounded repository mutation. C4 needs one production
adapter without moving execution authority into the SDK, duplicating
`aoa-playbooks` meaning, or creating a new always-on service.

The existing `aoa-governed-run` request is goal-shaped and its state uses two
sequential approval milestones. An SDK `RunPlan` is exact and typed. Treating
the playbook ID alone as proof of plan compatibility would hide the mapping
between plan steps and runtime phases.

## Options considered

- Let the SDK call governed-runner internals and own runtime state.
- Add a network service that accepts arbitrary plans.
- Re-implement governed execution as a second runner dedicated to the SDK.
- Add a narrow subprocess JSON bridge over the existing governed runner,
  backed by a versioned compatibility manifest and durable adapter state.

## Decision

`abyss-stack` owns `abyss_stack_agent_os_adapter_v1` under
`mechanics/governed-execution/parts/agent-os-adapter/`.

The adapter is exposed as an operator-local subprocess JSON bridge. It does
not listen on a port and is not enabled as a service. Every invocation names
an explicit state root and one operation. Session state, command receipts,
events, approval records, runtime evidence, and outcomes remain durable
runtime-owned artifacts beneath that root.

The bridge consumes exact `aoa-sdk` control-plane JSON and validates it with
the installed SDK contract package. It accepts no untyped fallback. A caller
must supply an exact binding that:

- identifies the governed request artifact already present in the plan input
  refs;
- binds the request file to its declared digest;
- supplies explicit local delivery coordinates for every pinned source and
  ABI observation;
- binds the exact runtime profile and adapter ABI.

For the Python bridge, the caller must also supply the absolute interpreter
containing that installed SDK package. The SDK subprocess transport invokes
it with `-I`; inherited `PYTHONPATH`, user-site packages, and the bridge
shebang are not package-selection authority.

The first compatibility entry admits only
`bounded_change_safe` / `AOA-P-0011`. It pins the reviewed
`aoa-playbooks` contour ABI, maps plan steps to governed-runner phases, and
maps two declared approval operations to `plan_freeze` and `landing`.
Unsupported scenarios, step sets, effects, snapshot observations, request
digests, approval shapes, or ABI versions fail before mutation.

The bridge delegates proposal, isolated preview, landing, validation,
rollback, and review-packet production to the existing governed runner. It
does not reinterpret eval candidates as verdicts or review packets as durable
memory. Runtime completion emits only runtime-owned evidence and outcome
references. Final eval, retention, and closeout composition remains an SDK C5
and stronger-owner workflow.

## Rationale

The subprocess boundary is explicit, local-first, and reversible. It avoids a
new daemon and keeps the SDK package independent of stack internals. The
compatibility manifest makes the governed-runner mapping inspectable and
versioned, while the exact snapshot binding prevents a path from becoming
artifact identity.

## Consequences

- Positive: `AoARunner` can drive one real stack-owned execution contour
  without acquiring execution authority.
- Positive: durable adapter state supports reconnect and restore across
  processes.
- Positive: the existing governed runner, policy, approvals, rollback, and
  evidence remain the only mutation implementation.
- Tradeoff: the adapter initially supports only one exact playbook contour.
- Tradeoff: `aoa-sdk` becomes a required runtime dependency for the bridge
  contract parser after the final release wave.
- Follow-up: C5 must compose external eval and memory refs without mutating
  the runtime-owned outcome.

## Source surfaces

- `mechanics/governed-execution/parts/agent-os-adapter/`
- `mechanics/governed-execution/parts/governed-runner/`
- `mechanics/governed-execution/parts/runtime-contracts/`
- `scripts/aoa-agent-os-runtime`
- `repo:aoa-sdk/docs/decisions/AOA-SDK-D-0080-bind-abyss-stack-through-an-explicit-runtime-transport.md`

## Follow-up route

Implement and validate the exact bounded-change bridge in a disposable target.
Do not add another scenario until its plan-to-runtime mapping and failure
behavior have deterministic coverage. Do not activate a service or widen
runtime target policy as part of this adapter landing.
