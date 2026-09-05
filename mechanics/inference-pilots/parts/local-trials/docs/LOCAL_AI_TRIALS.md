# LOCAL AI TRIALS

## Purpose

This document defines the bounded local-trial surface for supervised model trials on `abyss-stack`.

It is narrower than a proof layer and narrower than a benchmark-only surface:

- runtime truth stays local to `abyss-stack`
- per-case trial packets stay explicit and reviewable
- durable human+AI-readable summaries may be mirrored elsewhere
- no new HTTP APIs are introduced for the trial surface

## Placement map

This active document owns the local-trial route, truth-status boundaries, and
handoffs to benchmark, model-card, scenario, and governed-execution surfaces.

It does not keep the old step-by-step qualification narrative inline. The
historical command surface is preserved as a compatibility baseline routed
through the part-local compatibility runner.

Use role language for new work:

- `trial program`
- `qualification stage`
- `scenario`
- `benchmark family`
- `model profile`
- `model card`
- `promotion candidate`

Do not add new active programs with archived stage names. Existing old command
and artifact names remain documented under the legacy route only where
compatibility with runner output, runtime logs, or archived lineage requires
them.

## Current local model routes

Canonical local-worker path:
- `qwen-local-pilot-v1`
- `long-horizon-langgraph-llamacpp-v1`
- `bounded-autonomy-langgraph-llamacpp-v1`

Canonical runtime posture:
- preset: `intel-full`
- runtime path: `http://127.0.0.1:5403/run`
- backend: `llama.cpp`
- local Qwen posture:
  - `AOA_LLAMACPP_THREADS=4`
  - `AOA_LLAMACPP_BATCH_SIZE=512`
  - `AOA_LLAMACPP_CTX_SIZE=4096`
  - `AOA_LLAMACPP_CACHE_TYPE_K=f16`
  - `AOA_LLAMACPP_CACHE_TYPE_V=f16`
- orchestration: `LangGraph` for long-horizon, bounded-autonomy, and the current bounded local-worker posture

Explicit Intel 285H candidate overlays live under `compose/tuning/` and stay pilot-only until measured runtime packets promote one of them.

Durable program roots now in use:
- `qwen-local-pilot-v1`
- `langgraph-sidecar-pilot-v1`
- `qwen-llamacpp-pilot-v1`
- `long-horizon-langgraph-llamacpp-v1`
- `bounded-autonomy-langgraph-llamacpp-v1`

Old program ids for the same long-horizon and bounded-autonomy trial families
are retained only through the preserved trial compatibility route. Active docs should describe
those routes by role, not by old program numbering.

## Dual-surface reporting

Runtime truth root family:
- `${AOA_STACK_ROOT}/Logs/local-ai-trials/<program-id>/`

Durable human+AI-readable mirror family:
- `/srv/Dionysus/reports/local-ai-trials/<program-id>/`

Current durable program roots:
- `qwen-local-pilot-v1`
- `langgraph-sidecar-pilot-v1`
- `qwen-llamacpp-pilot-v1`
- `long-horizon-langgraph-llamacpp-v1`
- `bounded-autonomy-langgraph-llamacpp-v1`

Keep the split explicit:

- `abyss-stack` owns machine-readable trial truth and runtime-local artifacts
- `Dionysus` may mirror curated Markdown reports and trial digests
- do not move raw runtime truth into `Dionysus`
- do not let the mirror become a shadow owner of runtime behavior

## Packet shape

Each executed case must own one packet with:

- `case.spec.json`
- `run.manifest.json`
- `result.summary.json`
- `report.md`

Compatibility baseline index and closeout artifact names stay in the active
compatibility runner. The current owner-local runtime receipt log for
local-trial closeouts is:

- `/srv/AbyssOS/abyss-stack/.aoa/live_receipts/runtime-trial-closeouts.jsonl`

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

## Compatibility baseline bridge

The `scripts/aoa-local-ai-trials` helper remains the stable root wrapper for
the preserved baseline because existing runtime logs, closeout packets, and
compatibility checks still refer to that command surface.
The active part-local Python file is only a compatibility bridge; the preserved
runner implementation lives under
`mechanics/inference-pilots/parts/local-trials/compatibility-runners/aoa-local-ai-trials`.

For the old command sequence, stage details, and preserved mutation-safety
contract, use the active compatibility runner. The legacy index remains
provenance, not an execution backend.

The bridge does not:

- make the preserved baseline a first-run requirement
- introduce a new serving API
- upgrade runtime success into portable proof wording
- make old family names acceptable for new active trial topology
- treat an old routing case ID as current predecessor ownership
- validate or mutate an `aoa-routing` checkout; current routing owner checks
  use `aoa-sdk`, and predecessor W4 mutation cases remain legacy provenance

## Preserved mutation contract

The active compatibility runner retains `prepare-wave W4 --lane docs` and
`apply-case W4 <case-id>` as compatibility commands, not a new-work stage
taxonomy. Preparation produces `proposal.edit-spec.json`; `exact_replace`
and `anchored_replace` edits are applied deterministically inside the runner.
The `script_refresh` mode remains bounded to its declared generated surface.
`approval.status.json` and the isolated git worktree boundary remain required
by the runner's supervised mutation route. This contract does not authorize
running those commands, revive predecessor ownership, or supply approval.

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

Use [LANGGRAPH_PILOT](../../langgraph-pilot/docs/LANGGRAPH_PILOT.md) for the
sidecar contract.

That sidecar surface established the now-adopted execution posture:

- `aoa-local-ai-trials` remains the historical baseline for the step-gated qualification runner
- `LangGraph` is now the primary orchestration layer for long-horizon, bounded-autonomy, and the current bounded local-worker path
- `aoa-langgraph-pilot` remains the staged-edit comparison and fixture surface rather than the full execution baseline

## Long-Horizon Pilot

The next bounded scenario layer lives beside the compatibility baseline:

```bash
scripts/aoa-long-horizon-pilot materialize
scripts/aoa-long-horizon-pilot run-scenario <scenario-id> --until milestone
scripts/aoa-long-horizon-pilot resume-scenario <scenario-id>
scripts/aoa-long-horizon-pilot status --all
```

Use [PROVENANCE](../../../PROVENANCE.md) for the archived long-horizon source contract route.

The long-horizon runner:

- defaults to `http://127.0.0.1:5403/run`
- treats the canonical `llama.cpp` path as the primary substrate
- keeps `LangGraph` as the primary orchestration layer
- uses milestone gates instead of a monolithic archived stage command
- supports `read_only_summary`, `qwen_patch`, `script_refresh`, and `implementation_patch`
- reuses `approval.status.json` at `plan_freeze`, `first_mutation`, and `landing`
- keeps mutation scenarios worktree-first and explicitly approved before landing
- records one local checkpoint commit per successful mutation scenario when a tracked diff is present
- feeds a trial-local summary, not the canonical deployed autonomy verdict

## Bounded-Autonomy Pilot

The autonomy-focused layer lives beside long-horizon trials and keeps the same promoted substrate:

```bash
scripts/aoa-bounded-autonomy-pilot materialize
scripts/aoa-bounded-autonomy-pilot run-scenario <scenario-id> --until milestone
scripts/aoa-bounded-autonomy-pilot resume-scenario <scenario-id>
scripts/aoa-bounded-autonomy-pilot status --all
```

Use [PROVENANCE](../../../PROVENANCE.md) for the archived bounded-autonomy source contract route.

The bounded-autonomy runner:

- defaults to `http://127.0.0.1:5403/run`
- keeps `LangGraph` as the primary orchestration layer
- reduces approvals to `plan_freeze` and `landing`
- removes `first_mutation` from the normal mutation path
- keeps mutation scenarios worktree-first and explicitly approved before landing
- supports one bounded `autonomous_repair_loop` after `post_change_validation_failure`
- tracks `novel_implementation_passes`, `preexisting_noop_count`, `repair_attempted_count`, and `repair_success_count`
- still relies on `scripts/aoa-status --autonomy` for the deployed control-loop verdict

## Truth status

Use
[TRUTH_SURFACES](../../../../diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md)
when reading or publishing trial outcomes.

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

When you need the current control-loop status instead of a trial-local summary, use:

```bash
scripts/aoa-status --autonomy
scripts/aoa-status --autonomy --json
```

## Governed Execution After Bounded Autonomy

Long-horizon and bounded-autonomy trials remain pilot evidence.
The first governed mutation lane now lives at `scripts/aoa-governed-run`.
The canonical runtime contract for that lane is documented in
[GOVERNED_EXECUTION](../../../../governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md).

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
- may prepare bounded real-task requests from `config-templates/Configs/agent-api/governed-canary-catalog.json`
- now records trust evidence and operator triage instead of treating governed runs as opaque packets

## Relationship to runtime benchmarks

`aoa-qwen-bench` remains a bounded runtime benchmark helper.

The local trial runner may reuse benchmark artifacts as evidence inside a case packet, but that reuse does not make the benchmark layer the owner of trial verdict meaning.

Keep these boundaries:

- runtime bench evidence is local machine truth
- local trial packets are curated bounded case records
- portable proof belongs in `aoa-evals`, not here
