# Governed Execution Mechanic

## Mechanic card

Governed execution is the mechanic for bounded local-worker runs that can use
runtime tools while preserving review, gates, return policy, Agent OS
lifecycle bindings, and owner handoff.

### Trigger

Use this package when changing `aoa-governed-run`, the `aoa-sdk` Agent OS
runtime adapter, an external Codex incarnation/session, autonomy status, return
policy, candidate export, review packets, or local-worker execution records.

### abyss-stack owns

- runtime-side governed-run wrapper behavior
- local autonomy gate reporting
- return policy config shape
- candidate export plumbing
- runtime evidence refs for local-worker activity
- explicit Agent OS runtime admission, durable runtime state, and execution
  receipts
- exact external Codex launch, persistent thread/resume, runtime events,
  budget/effect observation, and reviewed-return export

### Stronger owner split

`aoa-skills`, `aoa-memo`, `aoa-evals`, `aoa-playbooks`, and owner repositories
own workflow, memory, proof, and playbook meaning. Runtime exports candidates
and receipts; owners decide acceptance.

### Inputs

Operator intent, runtime policy, advisory mirrors, local model worker outputs,
validation commands, and review packet destinations.

### Outputs

Governed run records, autonomy status JSON, memo or artifact candidates, and
bounded return packets.

### Must not claim

- autonomous authority
- owner acceptance
- proof verdict
- memory truth
- review completion from export alone

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [diagnostic-spine](../diagnostic-spine/README.md) for truth-goal status,
[runtime-repair](../runtime-repair/README.md) for repair-safe closeout, and
[federation-seams](../federation-seams/README.md) for advisory owner inputs.

## Active route

Current source surfaces stay in `mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`,
`mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py`,
`mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py`,
`mechanics/governed-execution/parts/agent-os-adapter/`,
`mechanics/governed-execution/parts/external-codex-agent/`,
`mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py`,
`scripts/aoa-governed-run`, `scripts/aoa-status`, candidate export wrappers,
config templates, and
package-local parts under `mechanics/governed-execution/parts/`.
