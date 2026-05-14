# W5 PILOT

## Purpose

This document defines the bounded W5 long-horizon supervised pilot for `abyss-stack`.

W5 is:

- scenario-based rather than one monolithic `run-wave`
- LangGraph-first for orchestration
- milestone-gated for human supervision
- llama.cpp-first on `http://127.0.0.1:5403/run`

W5 is not:

- a new public HTTP API
- a replacement for `aoa-local-ai-trials`
- an unbounded autonomy claim
- a license to collapse `trial_proven` into `live_available`

## Operator Surface

Use:

```bash
scripts/aoa-long-horizon-pilot materialize
scripts/aoa-long-horizon-pilot run-scenario <scenario-id> --until milestone|done
scripts/aoa-long-horizon-pilot resume-scenario <scenario-id>
scripts/aoa-long-horizon-pilot status --all
scripts/aoa-long-horizon-pilot status <scenario-id>
scripts/aoa-status --autonomy
```

Defaults:

- run URL: `http://127.0.0.1:5403/run`
- program id: `w5-langgraph-llamacpp-v1`
- runtime truth: `${AOA_STACK_ROOT}/Logs/local-ai-trials/w5-langgraph-llamacpp-v1/`
- mirror: `/srv/Dionysus/reports/local-ai-trials/w5-langgraph-llamacpp-v1/`

## Storage/runtime seam note

W5 stores pilot records only.

- the runtime truth directory is for bounded pilot evidence, not for service authority
- the mirror path is for reviewable copies of the same pilot records, not for runtime activation
- this seam does not add worker services, deployment control, certification, or governance power to `abyss-stack`
- the pilot record layer stays below the runtime body and above nothing except review

## Scenario Catalog

Materialize exactly these `8` scenarios in this order:

1. `runtime-inspect-langchain-health`
2. `runtime-inspect-route-api-health`
3. `runtime-inspect-platform-adaptation`
4. `evals-validate-and-explain`
5. `aoa-evals-contract-wording-alignment`
6. `aoa-routing-doc-boundary-alignment`
7. `aoa-routing-generated-surface-refresh`
8. `stack-sync-federation-check-mode`

Execution modes:

- `read_only_summary`
- `qwen_patch`
- `script_refresh`
- `implementation_patch`

The fixed recovery scenario is:

- `stack-sync-federation-check-mode`
- `force_pause_on_milestone = plan_freeze`

## Milestone Gates

Every scenario pauses at `plan_freeze`.

Mutation scenarios also pause at:

- `first_mutation`
- `landing`

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

W5 adds:

- `graph.state.json`
- `graph.history.jsonl`
- `interrupt.json`
- `approval.status.json`
- `scenario.plan.json`
- `step.journal.jsonl`
- `node-artifacts/`
- `worktree.manifest.json` for mutation scenarios
- `landing.diff` for landed mutation scenarios

Wave-level outputs:

- `W5-long-horizon-index.json`
- `W5-long-horizon-index.md`
- `W5_SUMMARY.md`

Each summary should also carry truth-status language from [TRUTH_SURFACES](../../../../diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md):

- `source_authored`
- `deployed`
- `trial_proven`
- `live_available`

For the current deployed control-loop verdict, use `scripts/aoa-status --autonomy` rather than treating the W5 summary as an operator health command.

## Boundaries

W5 keeps these constraints:

- read-only scenarios never create worktrees or commits
- mutation scenarios reuse the bounded W4 proposal and worktree posture
- every landing remains explicitly approved
- every successful mutation scenario records one local checkpoint commit when a tracked diff exists
- no push or PR creation is part of W5

The implementation scenario is intentionally narrow:

- `stack-sync-federation-check-mode`
- repo scope: `abyss-stack`
- allowed file: `scripts/aoa-sync-federation-surfaces`
- required behavior: add `--check` without widening sync semantics

## Gate

The hard W5 gate is:

- `pass_count == 8`
- `critical_failures == 0`
- `pause_resume_proved == true`
- `implementation_case_passed == true`
- `generated_case_passed == true`
- `unauthorized_scope_expansion == 0`
- `post_change_validation_failure == 0`

If the gate passes, the next action is:

`W5 passed on promoted llama.cpp + LangGraph. Use this substrate as the bounded baseline for the next autonomy-focused wave.`

That sentence still needs truth-status interpretation:

- W5 may be `trial_proven` before every related control surface is `live_available`
- a passing W5 packet does not override source-vs-deployed drift elsewhere in the stack
