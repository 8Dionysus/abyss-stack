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
