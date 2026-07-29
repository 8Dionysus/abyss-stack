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

Before execution the bridge verifies:

- exact runtime profile and adapter contract digest;
- exact plan, session, and binding;
- request provenance and raw file digest;
- raw file digest for every source and ABI location in the plan snapshot;
- a refreshed source/ABI observation immediately before every start, resume,
  or recovery dispatch, compared to the exact immutable plan before the
  backend can run;
- exact admitted scenario, playbook, contour ABI, active step set, and effect
  classes from `runtime-profile.v1.json`;
- exact typed scenario inputs and their original producer provenance;
- an A2A summon decision bound to the exact canonical summon-request digest
  and parent task identity, so a decision from another request cannot be mixed
  into an otherwise shape-compatible reviewed return;
- exact scenario-scoped runtime approval projection in `RuntimeProfile`;
- exact input and stack-owned output evidence requirements; caller-added or
  altered requirements are rejected rather than claimed by a generic bundle;
- the exact approval posture for the lane. Repository mutation requires the
  two governed `plan_freeze` and `landing` approvals; the admitted read-only
  lanes require none. The descriptor, profile projection, and compiled plan
  must agree in typed form;
- each decision targets the single current approval request and may be
  recorded only once. Stale or second decisions fail before durable approval,
  governed-runner, status, or outcome state changes;
- governed policy supplied through the profile constraint ref, with the full
  descriptor-declared owner, artifact, source, schema, and schema-version
  provenance plus the exact plan-snapshot digest;
- the complete evidence-requirement set equals the admitted runtime and
  scenario-input requirements; unknown producers or binding classes are not
  filtered away;
- every returned A2A artifact is a non-empty typed string before return review;
- an approved plan-freeze decision refreshes that same source/ABI snapshot
  before the governed preview backend can run;
- the start command and deterministic governed-run identity are atomically
  journaled before preparation. Exact replay reuses a matching durable result
  and fails closed on an incomplete or mismatched prior preparation.

The bridge never derives a request from a goal or playbook ID and never
searches for source paths.

## Lifecycle mappings

### Governed repository change

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

### Reviewed A2A return

```text
start
  -> inspect exact summon request/decision/reviewed child result
  -> emit runtime-owned target, return, checkpoint, eval-candidate, and
     dry-run closeout artifacts
  -> completed or failed(a2a_incomplete_return)
```

This lane does not summon or execute the child. A reviewed terminal child may
have failed and still support return when every expected artifact is present.
Missing output remains a typed runtime failure.

### Runtime degradation recovery

```text
start
  -> inspect exact operator-visible owner degradation receipt
  -> record bounded stress/re-entry artifacts
  -> paused

restore exact SessionHandle in a new Runner/process
resume
  -> revalidate the snapshot and owner receipt
  -> emit re-entry/proof-candidate/runtime-closeout artifacts
  -> completed
```

The contour's retry policy admits no hidden retry, so the lane uses explicit
durable pause/resume rather than forging a `RecoverCommand`. Rejection cancels
the Agent OS session. Exact command replay is effect-free; idempotency-key
payload drift is rejected. Applied command receipts bind the entire emitted
event slice and are persisted with runtime state.

## Evidence stop line

The bridge may emit a runtime evidence bundle containing governed-run or
lane-local artifacts. Scenario inputs cross the chain as original-owner refs;
the bridge does not re-sign them. It never turns a review-packet or proof
candidate into an eval verdict, memory receipt, checkpoint acceptance, or
final closeout receipt.

For C5 closeout, the SDK must first validate a complete immutable
`EvidenceChain`. Only its exact `CloseoutBundleRef` crosses this transport
boundary. The bridge validates that ref against its durable plan, session,
runtime outcome, and declared closeout-owner scope; it does not re-read or
reinterpret eval, memory, or checkpoint owner artifacts.
