# Project Runtime Approvals into Run Plans

- Decision ID: ABYSS-STACK-D-0100
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mechanics/governed-execution/parts/agent-os-adapter/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: runtime contract, approval policy, integration
- Stack lanes: runtime lane, federation seam, decision lane
- Mechanic parents: governed-execution
- Guard families: approval integrity, exact admission, owner evidence, no hidden execution
- Posture: accepted rationale

## Context

The runtime profile already declared the two exact approvals required by the
bounded repository-change lane and no approvals for the two read-only lanes.
The bridge correctly rejected any `RunPlan` that differed from that posture.

Before SDK compiler v3, however, the typed `RuntimeProfile` discarded the
scenario-specific approval projection. The bounded paired test therefore
inserted `plan_freeze` and `landing` into an example plan after compilation.
That tested runtime behavior but did not prove the public control-plane chain
could construct the admitted plan.

The bridge must not repair the gap by inventing approvals at dispatch time.
`AoARunner` requires the complete immutable approval set before session
preparation.

## Options considered

- Keep inserting runtime approvals into paired fixtures.
- Make routing predict runtime-specific effect gates.
- Let the bridge invent undeclared approvals after dispatch.
- Project the selected runtime-owner requirements before compilation.

## Decision

The `abyss_stack_agent_os_runtime_profile_v1` descriptor remains the owner of
each lane's `runtime_approval_requirements`.

The SDK-side owner-exact loader may select one explicit `scenario_id` and
project only that entry's requirements into
`RuntimeProfile.runtime_approval_requirements`. For the bounded lane the
projection contains `plan_freeze` and `landing`, both bound to `mutate`; A2A
return and degradation recovery project an empty tuple.

The bridge requires three exact representations to agree:

- the compatibility descriptor entry;
- the runtime-profile projection embedded in `RunPlan`;
- the plan's combined approval requirements.

Any difference fails before execution. Runtime profile projection grants no
approval and evaluates no policy; it only makes the runtime-owned requirement
visible before compilation.

## Rationale

The selected runtime knows which effect gates it requires, while routing owns
route eligibility. Carrying the runtime projection into compiler v3 preserves
both authorities and removes post-compilation fixture mutation.

## Consequences

- Positive: all three production-adapter success cycles now start from an
  unchanged plan built by the installed public SDK chain.
- Positive: read-only lanes remain free of repository-mutation approvals.
- Positive: the bridge retains fail-closed exact-plan admission.
- Tradeoff: a compilation-ready profile must select one exact scenario.
- Stop line: runtime approval projection is neither operator consent nor
  permission to execute.

## Currentness Review (2026-07-28)

Projection into the immutable plan is necessary but not sufficient for
decision admission. The runtime now accepts a decision only for the single
current request at its exact `plan_freeze` or `landing` lifecycle boundary,
and only when that request has no prior durable decision. The check happens
before the governed approval artifact, event stream, runtime status, or
outcome can change. Exact replay by decision ID remains effect-free; a second
decision with another ID is stale rather than new authority.

## Source surfaces

- `mechanics/governed-execution/parts/agent-os-adapter/runtime-profile.v1.json`
- `mechanics/governed-execution/parts/agent-os-adapter/aoa_agent_os_runtime.py`
- `mechanics/governed-execution/parts/agent-os-adapter/tests/`
- `repo:aoa-sdk/docs/decisions/AOA-SDK-D-0087-project-runtime-approvals-before-plan-compilation.md`

## Follow-up route

Keep runtime approval projection scenario-scoped and exact. A new conditional
gate requires a versioned runtime-profile decision and a new paired public
compiler-to-runtime proof.
