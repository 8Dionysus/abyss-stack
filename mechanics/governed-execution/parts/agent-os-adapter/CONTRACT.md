# Agent OS Runtime Bridge Contract

## Owner split

`aoa-sdk` owns routing, `RunPlan`, `AoARunner`, and the generic runtime adapter
protocol. `abyss-stack` owns this bridge, its state root, governed execution,
runtime approvals, runtime evidence, and runtime outcomes.

`aoa-playbooks` remains the owner of the admitted scenario contour.
`aoa-evals`, `aoa-memo`, checkpoint owners, and closeout owners retain their
verdict, retention, review, and closure authority.

## Invocation

```text
aoa-agent-os-runtime <operation> --state-root <absolute path>
```

For the Python implementation, production callers bind the installed SDK ABI
by invoking the bridge through the SDK transport's explicit absolute Python
interpreter:

```text
<absolute python interpreter> -I <absolute bridge path> <operation> --state-root <absolute path>
```

The isolated interpreter form is part of the delivery contract. A shebang,
`PATH`, `PYTHONPATH`, or user-site package must not choose which
`aoa_sdk.control_plane` ABI validates runtime state.

One JSON object is read from stdin. One
`abyss_stack_agent_os_bridge_response_v1` object is written to stdout. The
bridge has no network listener and starts no background service.

## Exact admission

Before mutation the bridge verifies:

- exact runtime profile and adapter contract digest;
- exact plan, session, and binding;
- request provenance and raw file digest;
- raw file digest for every source and ABI location in the plan snapshot;
- exact admitted scenario, playbook, contour ABI, active step set, and effect
  classes from `runtime-profile.v1.json`;
- exact stack-owned evidence requirements; caller-added or altered requirements
  are rejected rather than claimed by a generic runtime bundle;
- exactly two declared approval requirements, including owner, risk, step
  scope, evidence refs, expiry, and renewal posture, mapped to `plan_freeze`
  and `landing`;
- governed policy supplied through the profile constraint ref.

The bridge never derives a request from a goal or playbook ID and never
searches for source paths.

## Lifecycle mapping

```text
start
  -> governed preflight/proposal
  -> awaiting_approval(plan_freeze)

approve(plan_freeze)
  -> isolated governed preview
  -> paused + approval request(landing)

approve(landing)
  -> remains paused

resume
  -> governed landing + validation + rollback discipline
  -> completed or failed
```

Rejection cancels the Agent OS session. Exact command replay is effect-free;
idempotency-key payload drift is rejected. Applied command receipts bind the
entire emitted event slice and are persisted with the runtime state.

## Evidence stop line

The bridge may emit a runtime evidence bundle containing governed-run
artifacts and a runtime outcome referencing `result.summary.json`. It never
turns a review-packet candidate into an eval verdict, memory receipt,
checkpoint acceptance, or final closeout receipt.

For C5 closeout, the SDK must first validate a complete immutable
`EvidenceChain`. Only its exact `CloseoutBundleRef` crosses this transport
boundary. The bridge validates that ref against its durable plan, session,
runtime outcome, and declared closeout-owner scope; it does not re-read or
reinterpret eval, memory, or checkpoint owner artifacts.
