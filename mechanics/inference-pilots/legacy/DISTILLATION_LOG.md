# Inference Pilots Distillation Log

## 2026-05-07

Moved W5/W6 pilot docs and runner scripts into package-local legacy.

Still legacy:

- W5 and W6 raw wave docs
- W5 and W6 runner script names
- wave-specific status/index/summary vocabulary inside those runners

Current bridges:

- `scripts/aoa-long-horizon-pilot`
- `scripts/aoa-bounded-autonomy-pilot`

Future distillation should decide whether the long-horizon and autonomy pilots
need quiet active package scripts rather than compatibility bridges over the
old W5/W6 runners.

## 2026-05-13

Moved the W0-W4 local AI trial narrative out of the active first-run and
local-trials route docs into
`legacy/trials/raw/LOCAL_AI_TRIALS_W0_W4_BASELINE.md`.

Still compatibility-bound:

- `scripts/aoa-local-ai-trials run-wave`
- `scripts/aoa-local-ai-trials prepare-wave`
- `scripts/aoa-local-ai-trials apply-case`

The preserved runner implementation now lives at
`mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-local-ai-trials`; the
active part keeps only a compatibility bridge for the stable root command.
- W0-W4 runtime artifact names in existing local trial packets

Current active wording should use trial, scenario, benchmark, model-card, and
promotion language.

## 2026-05-13 trial legacy specialization

Moved the preserved W0-W6 trial/pilot docs and runner scripts under
`legacy/trials/` so trial lineage has one explicit archive home.

Still compatibility-bound:

- root quiet bridges for long-horizon and bounded-autonomy pilots
- `scripts/aoa-local-ai-trials` as a stable wrapper over the preserved runner
- old runtime packets that still name W0-W6 artifacts

New active trial topology must not add W-numbered route names.
