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
`AGENTS.md` lines. `AOA_SOURCE_ROOT` is a lookup coordinate and, when set, must
be accompanied by an absolute `AOA_SOURCE_IDENTITY` receipt with exact Git
`HEAD`/tree and selected source-surface digests; an environment receipt should
use the shared contract for all three consumers. An explicit foreign or isolated
worktree is therefore admitted only by its caller-supplied identity contract;
without an explicit contract, only the executing owner checkout is eligible.
Admission requires the shared identity helper and the invoked runner surface;
fixture-only roots, symlinked required directories, and symlinked parent
components of sealed surfaces fail closed. Non-mutating Git and worktree
operations run with a pinned root directory descriptor and sanitized `GIT_*`
environment, so Git discovery follows the selected root. Revalidation remains
a fail-closed drift detector; it is not described as an atomic pathname TOCTOU
closure. Policy `default_repo_root`, `$HOME/src`, `STACK_ROOT`, and deployed
projections are not implicit source bindings.
