# Governed Execution Provenance

This package descends from runtime runner, autonomy status, return policy, and
candidate export surfaces that originally depended on root scripts and scattered
docs for route clarity.

The refactor pattern is:

- keep operator-facing commands in `scripts/`
- keep implementation bodies under `mechanics/governed-execution/parts/`
- keep schemas, examples, and focused tests beside the part that owns the
  contract
- keep exported candidates as review material for stronger owners

## Owner Boundary

`abyss-stack` owns runtime-side execution records, wrappers, policy config
shape, and candidate export plumbing. `aoa-skills`, `aoa-memo`, `aoa-evals`,
`aoa-playbooks`, and owner repositories own workflow authority, memory truth,
proof verdicts, playbook meaning, and final acceptance.

## Current Bridges

- [PARTS.md](PARTS.md) maps governed-runner, autonomy-status, return-policy,
  runtime-contracts, candidate-exports, and local-worker-path parts.
- [parts/governed-runner/docs/GOVERNED_EXECUTION.md](parts/governed-runner/docs/GOVERNED_EXECUTION.md)
  owns governed execution posture.
- [parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md](parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md)
  owns bounded recurrence and return policy.
- [parts/local-worker-path/docs/CONTEXT_BUDGET_POLICY.md](parts/local-worker-path/docs/CONTEXT_BUDGET_POLICY.md)
  owns local-worker context-budget posture.
- [../federation-seams/README.md](../federation-seams/README.md) owns advisory
  owner inputs consumed by local-worker routes.
