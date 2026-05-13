# LOCAL AI TRIALS W0-W4 BASELINE

This file preserves the old W0-W4 local AI qualification narrative for
reproducibility and compatibility.

The active local-trials route is
`mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md`.
Do not treat this baseline as a first-run requirement or as the naming pattern
for new trial programs.

## Compatibility runner

Use the runtime helper only when replaying or maintaining the preserved
baseline:

```bash
scripts/aoa-local-ai-trials materialize
scripts/aoa-local-ai-trials run-wave W0
scripts/aoa-local-ai-trials run-wave W1
scripts/aoa-local-ai-trials run-wave W2
scripts/aoa-local-ai-trials run-wave W3
scripts/aoa-local-ai-trials prepare-wave W4 --lane docs
scripts/aoa-local-ai-trials apply-case W4 <case-id>
```

Optional backend/program override:

```bash
scripts/aoa-local-ai-trials --url http://127.0.0.1:5403/run --program-id qwen-llamacpp-pilot-v1 run-wave W0
```

What the helper does for this baseline:

- materializes contracts and frozen case specs for `W0` through `W4`
- writes planned `wave-index` surfaces for later compatibility phases
- executes `W0` on the intended local runtime path
- executes `W1` through grounded local snippets on the same `langchain-api /run` path
- executes `W2` through supervised read-only grounding on the same `langchain-api /run` path
- executes `W3` through grounded exact-only selection on the same `langchain-api /run` path
- prepares `W4` proposals through a staged supervised-edit flow
- applies approved `W4` cases only after isolated worktree validation
- runs one phase-aware `aoa skills dispatch --phase ingress` pass at `run-wave` start
- runs one phase-aware `aoa skills dispatch --phase pre-mutation` pass before any `W4 apply-case` mutation attempt
- restores the baseline after the parity sample
- writes stable `W*-closeout.{json,md}` aliases for compatibility handoff surfaces
- attempts one audit-only reviewed closeout submission into `aoa-sdk` when a phase reaches a terminal gate result
- appends one `runtime_trial_closeout_receipt` to the owner-local live receipt log for derived stats

What it does not do:

- it does not introduce a new serving API
- it does not upgrade runtime success into portable proof wording
- it does not collapse `W4` into a silent monolithic mutator

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
- treats fabricated refs, paths, URLs, or commands as hard failures across the whole baseline phase

## W3 exact-only selection execution

The `W3` runner:

- requires a green `W2` gate before execution
- captures local file refs and live HTTP source refs into `grounding.txt`, `prompt.txt`, and `evidence.summary.json`
- uses `aoa-qwen-run` with `temperature=0`, `max_tokens=48`, and an exact-only plain-text answer contract
- scores deterministically without a judge pass
- treats silent widening as a case failure
- treats unsafe-case mismatches or silent widening as phase-critical selection errors

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
- logs one `pre-mutation.dispatch.json` artifact per case so the operator can see `must_confirm` risk gates before mutation
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
