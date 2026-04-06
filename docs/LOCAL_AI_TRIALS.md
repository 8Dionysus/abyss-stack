# LOCAL AI TRIALS

## Purpose

This document defines the bounded local-trial surface for supervised model trials on `abyss-stack`.

It is narrower than a proof layer and narrower than a benchmark-only surface:

- runtime truth stays local to `abyss-stack`
- per-case trial packets stay explicit and reviewable
- durable human+AI-readable summaries may be mirrored elsewhere
- no new HTTP APIs are introduced for the trial surface

## Pilot lineage in this runtime

Canonical local-worker path:
- `qwen-local-pilot-v1`
- `w5-langgraph-llamacpp-v1`
- `w6-bounded-autonomy-llamacpp-v1`

Canonical runtime posture:
- preset: `intel-full`
- runtime path: `http://127.0.0.1:5403/run`
- backend: `llama.cpp`
- local Qwen posture:
  - `AOA_LLAMACPP_THREADS=4`
  - `AOA_LLAMACPP_BATCH_SIZE=512`
  - `AOA_LLAMACPP_CTX_SIZE=4096`
- orchestration: `LangGraph` for `W5`, `W6`, and the current bounded local-worker posture

Durable program roots now in use:
- `qwen-local-pilot-v1`
- `langgraph-sidecar-pilot-v1`
- `qwen-llamacpp-pilot-v1`
- `w5-langgraph-llamacpp-v1`
- `w6-bounded-autonomy-llamacpp-v1`

## Dual-surface reporting

Runtime truth root family:
- `${AOA_STACK_ROOT}/Logs/local-ai-trials/<program-id>/`

Durable human+AI-readable mirror family:
- `/srv/Dionysus/reports/local-ai-trials/<program-id>/`

Current durable program roots:
- `qwen-local-pilot-v1`
- `langgraph-sidecar-pilot-v1`
- `qwen-llamacpp-pilot-v1`
- `w5-langgraph-llamacpp-v1`
- `w6-bounded-autonomy-llamacpp-v1`

Keep the split explicit:

- `abyss-stack` owns machine-readable trial truth and runtime-local artifacts
- `Dionysus` may mirror curated Markdown reports and wave digests
- do not move raw runtime truth into `Dionysus`
- do not let the mirror become a shadow owner of runtime behavior

## Required packet shape

Each executed case must own one packet with:

- `case.spec.json`
- `run.manifest.json`
- `result.summary.json`
- `report.md`

Each wave must own:

- `wave-index.json`
- `wave-index.md`
- `W*-closeout.json`
- `W*-closeout.md`

When a wave reaches a terminal gate result (`pass` or `fail`), the runner also
attempts one bounded reviewed closeout handoff into `aoa-sdk` and records the
machine-readable result locally as:

- `W*-closeout.submit.json`

The same closeout step also publishes one owner-local runtime receipt to the
canonical stats intake log:

- `/srv/abyss-stack/.aoa/live_receipts/runtime-wave-closeouts.jsonl`

Each closeout submit result also gets a sibling artifact for direct inspection:

- `W*-closeout.submit.receipt.json`

The fixed report sections are:

- `Goal`
- `Inputs`
- `Expected Result`
- `Actual Result`
- `Evidence`
- `Boundary Check`
- `Verdict`
- `Failures`
- `Follow-up`

## Runner

Use the runtime helper:

```bash
scripts/aoa-local-ai-trials materialize
scripts/aoa-local-ai-trials run-wave W0
scripts/aoa-local-ai-trials run-wave W1
scripts/aoa-local-ai-trials run-wave W2
scripts/aoa-local-ai-trials run-wave W3
scripts/aoa-local-ai-trials prepare-wave W4 --lane docs
scripts/aoa-local-ai-trials apply-case W4 <case-id>
```

Optional backend/program overrides:

```bash
scripts/aoa-local-ai-trials --url http://127.0.0.1:5403/run --program-id qwen-llamacpp-pilot-v1 run-wave W0
```

What the helper does now:

- materializes contracts and frozen case specs for `W0` through `W4`
- writes planned wave indexes for later waves
- executes `W0` on the intended local runtime path
- executes `W1` through grounded local snippets on the same `langchain-api /run` path
- executes `W2` through supervised read-only grounding on the same `langchain-api /run` path
- executes `W3` through grounded exact-only selection on the same `langchain-api /run` path
- prepares `W4` proposals through a staged supervised-edit flow
- applies approved `W4` cases only after isolated worktree validation
- restores the baseline after the parity sample
- writes stable `W*-closeout.{json,md}` aliases for wave-level handoff surfaces
- attempts one audit-only reviewed closeout submission into `aoa-sdk` when a wave reaches a terminal gate result
- appends one `runtime_wave_closeout_receipt` to the owner-local live receipt log for derived stats

What it does not do:

- it does not introduce a new serving API
- it does not upgrade runtime success into portable proof wording
- it does not collapse `W4` into a silent monolithic mutator

## LangGraph sidecar origin and promoted role

The original comparison layer still exists:

```bash
scripts/aoa-langgraph-pilot materialize
scripts/aoa-langgraph-pilot run-case 8dionysus-profile-routing-clarity --until approval
scripts/aoa-langgraph-pilot resume-case 8dionysus-profile-routing-clarity
```

The same runner can also be pointed at an alternate backend/program root:

```bash
scripts/aoa-langgraph-pilot --url http://127.0.0.1:5403/run --program-id langgraph-sidecar-llamacpp-v1 run-case fixture-docs-wording-alignment --until approval
```

Use [LANGGRAPH_PILOT](LANGGRAPH_PILOT.md) for the sidecar contract.

That sidecar surface established the now-adopted execution posture:

- `aoa-local-ai-trials` remains the historical baseline for `W0` through `W4`
- `LangGraph` is now the primary orchestration layer for `W5`, `W6`, and the current bounded local-worker path
- `aoa-langgraph-pilot` remains the W4-shaped comparison and fixture surface rather than the full execution baseline

## W5 long-horizon pilot

The next bounded scenario layer lives beside the earlier waves:

```bash
scripts/aoa-w5-pilot materialize
scripts/aoa-w5-pilot run-scenario <scenario-id> --until milestone
scripts/aoa-w5-pilot resume-scenario <scenario-id>
scripts/aoa-w5-pilot status --all
```

Use [W5_PILOT](W5_PILOT.md) for the full W5 contract.

The W5 runner:

- defaults to `http://127.0.0.1:5403/run`
- treats the canonical `llama.cpp` path as the primary substrate
- keeps `LangGraph` as the primary orchestration layer
- uses milestone gates instead of a monolithic `run-wave W5`
- supports `read_only_summary`, `qwen_patch`, `script_refresh`, and `implementation_patch`
- reuses `approval.status.json` at `plan_freeze`, `first_mutation`, and `landing`
- keeps mutation scenarios worktree-first and explicitly approved before landing
- records one local checkpoint commit per successful mutation scenario when a tracked diff is present
- feeds a wave-local summary, not the canonical deployed autonomy verdict

## W6 bounded autonomy pilot

The autonomy-focused layer lives beside W5 and keeps the same promoted substrate:

```bash
scripts/aoa-w6-pilot materialize
scripts/aoa-w6-pilot run-scenario <scenario-id> --until milestone
scripts/aoa-w6-pilot resume-scenario <scenario-id>
scripts/aoa-w6-pilot status --all
```

Use [W6_PILOT](W6_PILOT.md) for the full W6 contract.

The W6 runner:

- defaults to `http://127.0.0.1:5403/run`
- keeps `LangGraph` as the primary orchestration layer
- reduces approvals to `plan_freeze` and `landing`
- removes `first_mutation` from the normal mutation path
- keeps mutation scenarios worktree-first and explicitly approved before landing
- supports one bounded `autonomous_repair_loop` after `post_change_validation_failure`
- tracks `novel_implementation_passes`, `preexisting_noop_count`, `repair_attempted_count`, and `repair_success_count`
- still relies on `scripts/aoa-status --autonomy` for the deployed control-loop verdict

## Truth status

Use [TRUTH_SURFACES](TRUTH_SURFACES.md) when reading or publishing trial outcomes.

Trial summaries should keep these fields separate:

- `source_authored`
- `deployed`
- `trial_proven`
- `live_available`

In particular:

- `trial_proven` is not the same thing as `live_available`
- a source-authored helper is not a live runtime surface until the deployed `Configs` copy is updated
- mirror Markdown in `Dionysus` may carry additive truth-status corrections without becoming the owner of runtime truth
- the deployed operator verdict for the promoted lane lives at `scripts/aoa-status --autonomy`

When you need the current control-loop status instead of a wave-local summary, use:

```bash
scripts/aoa-status --autonomy
scripts/aoa-status --autonomy --json
```

## Governed execution after W6

`W5` and `W6` remain pilot evidence.
The first governed mutation lane now lives at `scripts/aoa-governed-run`.
The canonical runtime contract for that lane is documented in [GOVERNED_EXECUTION](GOVERNED_EXECUTION.md).

Use:

```bash
scripts/aoa-governed-run prepare-request --write /tmp/governed-request.json
scripts/aoa-governed-run prepare-canary docs-truth-wording-alignment --write /tmp/governed-request.json
scripts/aoa-governed-run materialize-canaries --write-dir /tmp/governed-canaries
scripts/aoa-governed-run run --request-file /tmp/governed-request.json --until done
scripts/aoa-governed-run resume <run-id>
scripts/aoa-governed-run status --all --explain
```

This lane:

- still fails closed on `aoa-status --autonomy --json`
- resolves playbook and memo context through the existing advisory seams
- writes `approval.status.json` at `plan_freeze` and `landing`
- validates mutations inside an isolated git worktree before landing
- records `landing.diff` and `worktree.manifest.json` before main-checkout apply
- writes `rollback.status.json` if post-apply validation fails
- keeps runtime execution permissions in `config-templates/Configs/agent-api/governed-execution-policy.yaml`
- may seed bounded real-task requests from `config-templates/Configs/agent-api/governed-canary-catalog.json`
- now records trust evidence and operator triage instead of treating governed runs as opaque packets

## W1 grounded execution

Use:

```bash
scripts/aoa-qwen-run --prompt-file /tmp/example.prompt.txt --json
```

The `W1` runner:

- reads only local text `source_refs`
- stores bounded grounded excerpt capture in `grounding.txt`
- builds `prompt.txt` from compact prompt slices derived from the same local refs
- calls `aoa-qwen-run` with `temperature=0`
- scores exact repo ownership and boundary confusion cases without introducing new HTTP APIs

## W2 supervised read-only execution

The `W2` runner:

- requires a green `W1` gate before execution
- captures local refs, HTTP `GET` evidence, and declared read-only command outcomes before prompting Qwen
- stores `grounding.txt`, `prompt.txt`, `judge.prompt.txt`, and `evidence.summary.json` per case
- uses a compact JSON answer contract instead of free-form prose
- runs a second bounded judge pass through `aoa-qwen-run`
- allows honest non-zero read-only command outcomes when the model reports them accurately and preserves boundaries
- treats fabricated refs, paths, URLs, or commands as hard failures across the whole wave

## W3 exact-only selection execution

The `W3` runner:

- requires a green `W2` gate before execution
- captures local file refs and live HTTP source refs into `grounding.txt`, `prompt.txt`, and `evidence.summary.json`
- uses `aoa-qwen-run` with `temperature=0`, `max_tokens=48`, and an exact-only plain-text answer contract
- scores deterministically without a judge pass
- treats silent widening as a case failure
- treats unsafe-case mismatches or silent widening as wave-critical selection errors

## W4 staged supervised edits

The `W4` runner uses staged commands instead of `run-wave W4`.

Use:

```bash
scripts/aoa-local-ai-trials prepare-wave W4 --lane docs
scripts/aoa-local-ai-trials prepare-wave W4 --lane generated
scripts/aoa-local-ai-trials apply-case W4 <case-id>
```

The `W4` flow:

- requires a green `W3` gate before proposal preparation or apply
- keeps docs-only and generated-refresh cases in separate lanes
- prepares one proposal packet per case without mutating the target repo
- keeps the public `prepare-wave W4` and `apply-case W4` interface stable while using a smaller staged internal docs flow
- runs docs-lane `qwen_patch` preparation in four internal steps: `target-selection`, `alignment-plan`, `edit-spec exact`, and `edit-spec anchor fallback`
- trims applicable root and nested `AGENTS.md` guidance to a bounded heading whitelist instead of copying full guide files into docs prompts
- uses a hybrid docs mutation contract: `exact_replace` first, then `anchored_replace` if exact replacement is unavailable or ambiguous
- fails closed when an edit-spec cannot be applied uniquely
- builds `proposal.diff` deterministically inside the runner instead of accepting model-written raw unified diffs
- uses `script_refresh` mode for generated cases and records the frozen builder command instead of asking the model for a diff
- creates `approval.status.json` per case and requires explicit `approved` status before any mutation
- runs every mutation first in an isolated git worktree
- validates touched files against the frozen allowed-file scope before landing
- reruns acceptance checks in the main repo only after the worktree passes
- blocks generated-lane apply until docs lane has at least `5/6` passes and zero critical failures
- continues docs-lane preparation across all cases even if one proposal is invalid

W4-specific artifacts include:

- `proposal.target.json`
- `proposal.plan.json`
- `proposal.edit-spec.json`
- `proposal.prompt.txt`
- `proposal.retry.prompt.txt`
- `proposal.diff`
- `proposal.summary.json`
- `approval.status.json`
- `worktree.manifest.json`

W4 critical failures remain:

- `unauthorized_scope_expansion`
- `post_change_validation_failure`

## Relationship to runtime benchmarks

`aoa-qwen-bench` remains a bounded runtime benchmark helper.

The local trial runner may reuse benchmark artifacts as evidence inside a case packet, but that reuse does not make the benchmark layer the owner of trial verdict meaning.

Keep these boundaries:

- runtime bench evidence is local machine truth
- local trial packets are curated bounded case records
- portable proof belongs in `aoa-evals`, not here
