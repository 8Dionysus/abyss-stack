# GOVERNED EXECUTION

This document defines the first governed mutation lane after the promoted `W5/W6` autonomy pilots.

The default stance is intentionally narrow:

- the gate is fail-closed
- the first repo scope is `abyss-stack` only
- the operator surface is CLI-first through `scripts/aoa-governed-run`
- `route-api` and `langchain-api /run/federated` remain advisory surfaces, not mutation-permission surfaces

## Canonical runtime policy

The public-safe runtime policy lives at:

```text
${AOA_STACK_ROOT}/Configs/agent-api/governed-execution-policy.yaml
```

The source-managed template lives at:

```text
config-templates/Configs/agent-api/governed-execution-policy.yaml
```

This policy owns runtime execution permissions only.
It does not redefine playbook meaning, route meaning, or memo canon.

## Request shape

Use `scripts/aoa-governed-run prepare-request --write <path>` to create a request template.

The request contract is runtime-owned and JSON-shaped:

- `goal`
- `playbook_id` or `playbook_select`
- optional `memo`
- `profile_class`
- `repo_root`
- optional `break_glass_reason`

The first governed wave is mutation-only and `abyss-stack`-only.

## Execution flow

`scripts/aoa-governed-run` supports:

```bash
scripts/aoa-governed-run prepare-request --write /tmp/request.json
scripts/aoa-governed-run run --request-file /tmp/request.json --until done
scripts/aoa-governed-run resume <run-id>
scripts/aoa-governed-run status --all
scripts/aoa-governed-run status <run-id>
```

The flow is:

1. preflight
2. advisory context resolution through `route-api /playbooks/inspect|select` and `/memo/recall-contract`
3. fail-closed gate check through `aoa-status --autonomy --json`
4. proposal preparation without mutating the repo
5. `plan_freeze` approval through `approval.status.json`
6. isolated worktree preview with one bounded repair max
7. `landing` approval through `approval.status.json`
8. landing diff apply back to the main checkout
9. post-apply validation and automatic rollback on failure

The main checkout is never repaired autonomously after landing.
Only the isolated worktree may use the bounded repair budget.

## Minimum packet set

Each run writes under:

```text
${AOA_STACK_ROOT}/Logs/governed-runs/<run-id>/
```

Minimum packet set:

- `request.json`
- `preflight.summary.json`
- `policy.snapshot.json`
- `approval.status.json`
- `worktree.manifest.json`
- `landing.diff`
- `rollback.status.json` when needed
- `result.summary.json`
- `report.md`

Additional proposal artifacts may be written under `artifacts/` to keep review legible.

## Failure classes

Stable machine-readable failure classes are:

- `autonomy_gate_failed`
- `policy_denied`
- `approval_missing`
- `scope_violation`
- `proposal_invalid`
- `post_change_validation_failure`
- `rollback_failed`

Examples:

- dirty repo or `base_head` drift map to `policy_denied`
- out-of-scope file touches map to `scope_violation`
- invalid edit-spec or empty landing diff maps to `proposal_invalid`
- failed main-checkout validation with successful reverse-apply still maps to `post_change_validation_failure`
- failed reverse-apply maps to `rollback_failed`

## Approval posture

This wave keeps approvals explicit and file-backed.

`approval.status.json` is the pause/resume seam.
Operators review proposal artifacts at `plan_freeze`, then review `landing.diff` and `worktree.manifest.json` at `landing`.

Break-glass may bypass only the `aoa-status --autonomy --json` pass gate, and only when:

- the selected playbook policy allows it
- `break_glass_reason` is present

Break-glass does not widen repo scope, file scope, approval requirements, or rollback behavior.

## Boundaries

Do not blur these boundaries:

- `aoa-playbooks` still owns playbook meaning
- `route-api` still owns the advisory inspection seam
- `langchain-api /run/federated` still contributes advisory context only
- `abyss-stack` owns runtime permission semantics and landing discipline

This makes the promoted autonomy lane more governable without turning the stack into the doctrine owner for sibling repos.
