# W6 PILOT

## Purpose

This document defines the bounded `W6` autonomy pilot for `abyss-stack`.

W6 is:

- scenario-based rather than a monolithic `run-wave`
- LangGraph-first for orchestration
- llama.cpp-first on `http://127.0.0.1:5403/run`
- reduced-touch, with approval gates at `plan_freeze` and `landing` only

W6 is not:

- a new public HTTP API
- a replacement for `aoa-local-ai-trials`, `aoa-langgraph-pilot`, or `aoa-w5-pilot`
- an unbounded autonomy claim
- a license to collapse `trial_proven` into `live_available`

## Operator Surface

Use:

```bash
scripts/aoa-w6-pilot materialize
scripts/aoa-w6-pilot run-scenario <scenario-id> --until milestone|done
scripts/aoa-w6-pilot resume-scenario <scenario-id>
scripts/aoa-w6-pilot status --all
scripts/aoa-w6-pilot status <scenario-id>
scripts/aoa-status --autonomy
```

Defaults:

- run URL: `http://127.0.0.1:5403/run`
- program id: `w6-bounded-autonomy-llamacpp-v1`
- runtime truth: `${AOA_STACK_ROOT}/Logs/local-ai-trials/w6-bounded-autonomy-llamacpp-v1/`
- mirror: `/srv/Dionysus/reports/local-ai-trials/w6-bounded-autonomy-llamacpp-v1/`

## Scenario Catalog

Materialize exactly these `6` scenarios in this order:

1. `runtime-inspect-langchain-health`
2. `runtime-inspect-route-api-health`
3. `aoa-evals-contract-wording-alignment`
4. `aoa-routing-generated-surface-refresh`
5. `stack-sync-federation-json-check-report`
6. `llamacpp-pilot-verify-command`

Execution modes:

- `read_only_summary`
- `qwen_patch`
- `script_refresh`
- `implementation_patch`

Novel implementation scenarios:

- `stack-sync-federation-json-check-report`
- `llamacpp-pilot-verify-command`

The fixed pause/resume proof scenario is:

- `llamacpp-pilot-verify-command`
- `force_pause_on_milestone = landing`

## Milestone Gates

Every scenario pauses at `plan_freeze`.

Mutation scenarios also pause at:

- `landing`

`first_mutation` is intentionally removed from the normal `W6` path.

Approval state is written into `approval.status.json` with:

- `milestone_id`
- `milestone_status`
- `approved`
- `approved_at`
- `notes`

## Artifacts

Each scenario keeps the standard packet:

- `case.spec.json`
- `run.manifest.json`
- `result.summary.json`
- `report.md`

W6 adds:

- `graph.state.json`
- `graph.history.jsonl`
- `interrupt.json`
- `approval.status.json`
- `scenario.plan.json`
- `step.journal.jsonl`
- `node-artifacts/`
- `worktree.manifest.json`
- `landing.diff`

Wave-level outputs:

- `W6-autonomy-index.json`
- `W6-autonomy-index.md`
- `W6_SUMMARY.md`

Each summary should also carry truth-status language from [TRUTH_SURFACES](TRUTH_SURFACES.md):

- `source_authored`
- `deployed`
- `trial_proven`
- `live_available`

For the current deployed control-loop verdict, use `scripts/aoa-status --autonomy` rather than treating the W6 summary as an operator health command.

## Boundaries

W6 keeps these constraints:

- read-only scenarios never create worktrees or commits
- mutation scenarios reuse the bounded W4 proposal and worktree posture
- `autonomous_repair_loop` may retry at most once and only after `post_change_validation_failure`
- repair must stay inside the same `allowed_files`
- landing remains explicitly approved
- every successful mutation scenario records one local checkpoint commit when a tracked diff exists
- no push or PR creation is part of W6

The two new implementation scenarios are intentionally narrow:

- `stack-sync-federation-json-check-report`
  - repo scope: `abyss-stack`
  - allowed file: `scripts/aoa-sync-federation-surfaces`
  - required behavior: add `--json` for `--check`

- `llamacpp-pilot-verify-command`
  - repo scope: `abyss-stack`
  - allowed file: `scripts/aoa-llamacpp-pilot`
  - required behavior: add a bounded `verify` subcommand

Neither implementation scenario may pass as `preexisting-noop`.

## Gate

The hard W6 gate is:

- `pass_count == 6`
- `critical_failures == 0`
- `pause_resume_proved == true`
- `novel_implementation_passes == 2`
- `generated_case_passed == true`
- `implementation_case_passed == true`
- `preexisting_noop_count == 0`
- `unauthorized_scope_expansion == 0`
- `post_change_validation_failure == 0`

Repair metrics are mandatory to record:

- `repair_attempted_count`
- `repair_success_count`

But they are not hard-gate fields for W6.

If the gate passes, the next action is:

`W6 passed on the promoted llama.cpp + LangGraph autonomy track. Use this substrate and approval posture as the baseline for the next implementation-heavy autonomy wave.`

That sentence still needs truth-status interpretation:

- W6 can be `trial_proven` before the same control surfaces are deployed into `/srv/abyss-stack/Configs`
- W6 is not `live_available` for a given control feature until the deployed operator path exposes it
