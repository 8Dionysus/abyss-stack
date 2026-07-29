# GOVERNED EXECUTION

This document defines the governed mutation lane after the preserved autonomy pilot evidence.

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

The same runtime family now also carries a public-safe canary catalog at:

```text
${AOA_STACK_ROOT}/Configs/agent-api/governed-canary-catalog.json
```

That catalog exists to prepare real bounded `abyss-stack` canary tasks.
It does not replace the policy and it does not authorize execution by itself.

## Request shape

Use `scripts/aoa-governed-run prepare-request --write <path>` to create a request template.

The request contract is runtime-owned and JSON-shaped:

- `goal`
- `playbook_id` or `playbook_select`
- optional `memo`
- `profile_class`
- `repo_root`
- optional `break_glass_reason`
- optional `canary_id`
- optional `task_class`

An `abyss-stack` checkout is admitted only when its canonical owner markers are
present, including `docs/install/DEPLOYMENT.md`; the retired
`docs/DEPLOYMENT.md` path is not a valid checkout marker.

The green repo-scope expansion gate serves as evidence for later review only; it does not widen governed repo scope implicitly during the current governed run. The default governed target remains mutation-only and `abyss-stack`-owned, while any external target still requires explicit policy coverage and evidence-backed scope promotion.

For canary preparation, use:

```bash
scripts/aoa-governed-run prepare-canary docs-truth-wording-alignment --write /tmp/governed-request.json
scripts/aoa-governed-run materialize-canaries --write-dir /tmp/governed-canaries/
```

## Execution flow

`scripts/aoa-governed-run` supports:

```bash
scripts/aoa-governed-run prepare-request --write /tmp/request.json
scripts/aoa-governed-run prepare-canary docs-truth-wording-alignment --write /tmp/request.json
scripts/aoa-governed-run materialize-canaries --write-dir /tmp/governed-canaries
scripts/aoa-governed-run run --request-file /tmp/request.json --until done
scripts/aoa-governed-run resume <run-id>
scripts/aoa-governed-run audit <run-id>
scripts/aoa-governed-run replay-review-packets <run-id>
scripts/aoa-governed-run status --all
scripts/aoa-governed-run status <run-id>
scripts/aoa-governed-run status --all --explain
scripts/aoa-governed-run status <run-id> --explain
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
10. bounded review-packet materialization under `${AOA_STACK_ROOT}/Logs/governed-runs/<run-id>/artifacts/`

The main checkout is never repaired autonomously after landing.
Only the isolated worktree may use the bounded repair budget.
When review-packet inputs are available, the governed lane writes:

- `artifacts/advisory_trace.json`
- `artifacts/review_packet_manifest.json`
- `artifacts/review_packet_audit.json`
- bounded raw input payloads for existing memo/eval export wrappers

Those packets remain runtime-owned candidates until human review in the owner repos.
`audit <run-id>` computes operator-facing packet readiness without mutating owner repos.
`replay-review-packets <run-id>` reruns only the review-packet assembly lane from stored request, preflight, and advisory context.

## Trust states and promotion rubric

The governed lane now distinguishes three trust states:

- `experimental`
- `canary_proven`
- `trusted`

Configured trust state still comes from `${AOA_STACK_ROOT}/Configs/agent-api/governed-execution-policy.yaml`.
Observed trust state comes from actual governed run evidence under `${AOA_STACK_ROOT}/Logs/governed-runs/`.

Promotion remains evidence-based rather than implicit:

- `canary_proven` requires repeated successful runs with zero scope, rollback, break-glass, and post-change validation drift
- `trusted` requires a broader run count and multiple successful task classes
- repo-scope expansion remains a separate gate and is not implied by one playbook becoming trusted

This keeps the default lane inside `abyss-stack` until the operator has real evidence rather than mechanism-only confidence, even though bounded external-target policy support may already exist under explicit review.

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

The run root also acts as the evidence source for:

- per-playbook promotion summaries
- repo-scope expansion gate checks
- operator triage such as `blocked_reason`, `resumable`, and `recommended_action`

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

## Operator triage

`scripts/aoa-governed-run status` now carries a compact triage layer:

- `terminal`
- `resumable`
- `operator_action_required`
- `blocked_reason`
- `recommended_action`
- `safe_resume_command` when resumption is valid

When review packets exist, `status --explain` also surfaces:

- `audit_verdict`
- blocked or missing packet kinds
- recommended review targets
- `safe_replay_command` when the stored run is replayable

Use `--explain` when you want a one-screen summary instead of raw JSON.

`status --all` also carries:

- playbook-level observed vs configured trust state
- repo-scope expansion gate status
- blocked-run count and latest operator action

## Approval posture

This lane keeps approvals explicit and file-backed.

`approval.status.json` is the pause/resume seam.
Operators review proposal artifacts at `plan_freeze`, then review `landing.diff` and `worktree.manifest.json` at `landing`.

Break-glass may bypass only the `aoa-status --autonomy --json` pass gate, and only when:

- the selected playbook policy allows it
- `break_glass_reason` is present

Break-glass does not widen repo scope, file scope, approval requirements, or rollback behavior.

Approval artifacts are now checked against the governed run state before resume.
If `approval.status.json` no longer matches `run_id`, `base_head`, or milestone shape, the run fails closed instead of silently resuming.

## Boundaries

Do not blur these boundaries:

- `aoa-playbooks` still owns playbook meaning
- `route-api` still owns the advisory inspection seam
- `langchain-api /run/federated` still contributes advisory context only
- `abyss-stack` owns runtime permission semantics and landing discipline

This makes the promoted autonomy lane more governable without turning the stack into the doctrine owner for sibling repos.
