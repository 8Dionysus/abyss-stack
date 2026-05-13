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
local-trials route docs into `legacy/raw/LOCAL_AI_TRIALS_W0_W4_BASELINE.md`.

Still compatibility-bound:

- `scripts/aoa-local-ai-trials run-wave`
- `scripts/aoa-local-ai-trials prepare-wave`
- `scripts/aoa-local-ai-trials apply-case`
- W0-W4 runtime artifact names in existing local trial packets

Current active wording should use trial, scenario, benchmark, model-card, and
promotion language.
