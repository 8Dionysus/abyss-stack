# Owner-Bound Agent OS Execution Lanes

- Decision ID: ABYSS-STACK-D-0099
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mechanics/governed-execution/parts/agent-os-adapter/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: runtime contract, integration, governed execution
- Stack lanes: runtime lane, federation seam, decision lane
- Mechanic parents: governed-execution
- Guard families: exact admission, owner evidence, durable lifecycle, no hidden execution
- Posture: accepted rationale

## Context

The first Agent OS bridge admitted only the repository-mutation contour
`bounded_change_safe` / `AOA-P-0011` and therefore equated the whole adapter
with governed-runner phases and two mutation approvals. The shared SDK
contracts also express reviewed A2A return and runtime-degradation recovery
contours. Pretending those read-only contours were governed repository changes
would add meaningless approvals, hide their typed inputs, and misrepresent
runtime, eval, checkpoint, and memory authority.

The alternative pressure is equally unsafe: a generic plan interpreter inside
`abyss-stack` would re-author `aoa-playbooks` meaning and turn the runtime
bridge into a hidden orchestrator.

## Options considered

- Keep one repository-mutation lane and treat the other golden scenarios as
  SDK-only tests.
- Force every scenario through the governed runner and its two approval
  milestones.
- Accept arbitrary read-only plans and infer their behavior from step names.
- Keep one transport and durable lifecycle contract while admitting a small
  exact set of owner-pinned execution lanes.

## Decision

`abyss_stack_agent_os_adapter_v1` keeps one subprocess transport, one exact
runtime profile, and one durable session/event store, but its compatibility
manifest names the execution lane for every admitted scenario:

- `governed_repository_change` delegates `AOA-P-0011` mutation to the existing
  governed runner and preserves both explicit approvals;
- `a2a_return_review` consumes the exact typed `summon_request`,
  `summon_decision`, and reviewed `child_task_result`, emits only bounded
  runtime return/checkpoint/eval candidates, and fails closed on an incomplete
  return;
- `runtime_degradation_recovery` consumes one operator-visible
  `service_degradation_receipt_v1`, records partial bounded evidence, pauses
  durably, and completes only after an exact `SessionHandle` resume.

Every lane pins one `aoa-playbooks` contour ABI, exact active steps, exact
typed inputs, exact evidence requirements, and exact approval posture.
Repository mutation still flows only through the governed runner. Read-only
lanes execute no model, tool, child agent, service restart, network call, or
sibling-repository mutation.

Scenario-input evidence keeps the original producer provenance. The adapter
may retain and carry those refs into the evidence chain, but it does not
re-sign `aoa-summon` evidence as `abyss-stack`. Stack-owned output bundles
remain runtime evidence only and never become eval verdicts, memo receipts,
checkpoint acceptance, or closeout authority.

## Rationale

Lane identity makes the runtime mapping inspectable without creating a second
playbook language. Exact inputs and failure behavior prevent step-name
heuristics. Reusing the subprocess and durable lifecycle contract preserves
restore, idempotency, event ordering, and source/ABI drift checks across all
three scenarios while keeping mutation policy in its existing owner.

## Consequences

- Positive: all three control-plane golden scenarios have a real
  `abyss-stack` adapter cycle.
- Positive: A2A and degradation trials do not pay repository-mutation approval
  or governed-runner cost when they perform no mutation.
- Positive: runtime restore is proven across a new subprocess before
  degradation resume.
- Tradeoff: every new scenario still needs an explicit compatibility entry,
  failure matrix, and paired SDK/runtime proof.
- Tradeoff: A2A child execution remains external; this lane reviews a returned
  artifact chain and must not claim it summoned the child.
- Follow-up: isolated agent trials must exercise successful, conflicting, and
  incomplete returns without granting test agents architecture authority.

## Source surfaces

- `mechanics/governed-execution/parts/agent-os-adapter/`
- `mechanics/runtime-repair/parts/degradation-receipts/`
- `mechanics/runtime-repair/parts/a2a-return-dry-run/`
- `repo:aoa-sdk/src/aoa_sdk/runtime_adapters/abyss_stack.py`
- `repo:aoa-playbooks/mechanics/scenario-composition/parts/plan-contours/`

## Follow-up route

Keep the paired installed-wheel runtime suite green, then run bounded
fresh-context and multi-agent trials. Do not add a generic plan interpreter,
move owner verdicts into the adapter, or widen mutation policy.
