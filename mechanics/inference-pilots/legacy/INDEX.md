# Inference Pilots Legacy Index

## Trial Legacy

Old trial and pilot docs now live in `legacy/trials/raw/`:

- `docs/W5_PILOT.md`
- `docs/W6_PILOT.md`
- W0-W4 local AI trial baseline narrative:
  `legacy/trials/raw/LOCAL_AI_TRIALS_W0_W4_BASELINE.md`

Old trial runner scripts now live under `legacy/trials/artifacts/scripts/`:

- `scripts/aoa-local-ai-trials` preserved compatibility backend
- `scripts/aoa-w5-pilot`
- `scripts/aoa-w6-pilot`

## Active Bridges

Use these root bridge commands for current operator entry:

- `scripts/aoa-long-horizon-pilot`
- `scripts/aoa-bounded-autonomy-pilot`

Those bridges execute the legacy runner files while keeping the root command
surface quieter.

The `scripts/aoa-local-ai-trials` command remains an active compatibility
wrapper because current runtime packets and closeout records still use its
W0-W4 command names. Its preserved runner now lives at
`legacy/trials/artifacts/scripts/aoa-local-ai-trials`, and its wave-era narrative
routes through `legacy/trials/raw/LOCAL_AI_TRIALS_W0_W4_BASELINE.md`. New active trial
topology should use trial, scenario, benchmark, model-card, and promotion
language instead.
