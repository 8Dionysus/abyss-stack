# 2026-05-13 Local AI Trials First-Run Boundary

## Status

Accepted.

## Context

`docs/FIRST_RUN.md` had grown a local AI qualification step that exposed the
old W0-W4 `aoa-local-ai-trials` flow as if it were part of the ordinary first
runtime launch. That mixed two different jobs:

- first-run bootstrap and smoke validation of the selected runtime profile
- optional supervised model trials, runtime benchmarks, model-fit notes, and
  promotion evidence

The W0-W4 command names are still present in the compatibility runner and in
existing runtime artifacts, but they are not the naming pattern for new active
trial topology.

## Decision

Keep `FIRST_RUN` focused on source checkout to running runtime profile.

Route local model trials through
`mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md`, runtime
benchmark packets through `RUNTIME_BENCH_POLICY.md`, and model-family or
variant fit notes through
`mechanics/machine-fit/parts/inference-tuning/docs/MODEL_CARDS.md`.

Preserve the old W0-W4 qualification narrative under
`mechanics/inference-pilots/legacy/trials/raw/LOCAL_AI_TRIALS_W0_W4_BASELINE.md`.
Preserve the old runner implementation under
`mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-local-ai-trials`,
with `mechanics/inference-pilots/parts/local-trials/aoa_local_ai_trials.py`
kept as a thin compatibility bridge for the stable root command.

## Consequences

- first-run docs no longer tell operators to run a historical local-model
  benchmark as a normal bootstrap step
- active trial docs use trial, scenario, benchmark, model-card, and promotion
  language
- the W0-W4 command surface remains available through the compatibility bridge
  for existing logs and closeout packets
- validators now check active route wording separately from the preserved
  compatibility baseline
