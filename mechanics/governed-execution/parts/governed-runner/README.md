# Governed Runner

Routes `scripts/aoa-governed-run`,
`mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py`,
`mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py`,
`mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`,
and the focused tests under `tests/`.

The runner remains bounded by policy, gates, and explicit operator approval.

## Source binding

The governed target accepts only the exact `abyss-stack` source contract: the
required source shape, first non-empty `README.md` line `# abyss-stack`, and
exact 'Root route card for `abyss-stack`.' owner line within the first eight
`AGENTS.md` lines. `AOA_SOURCE_ROOT` is authoritative when set; an invalid
explicit binding fails closed. Without it, only the executing owner-qualified
source checkout is eligible. Policy `default_repo_root`, `$HOME/src`,
`STACK_ROOT`, and deployed projections are not implicit source bindings.
