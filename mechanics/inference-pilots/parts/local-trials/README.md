# Inference Pilot Surface Contracts

This directory keeps inference-pilot machine-readable benchmark surfaces
package-local.

- `docs/LOCAL_AI_TRIALS.md` owns the local trial route narrative.
- `docs/RUNTIME_BENCH_POLICY.md` owns benchmark evidence posture.
- `schemas/` defines runtime benchmark manifest contracts.
- `examples/` carries public-safe benchmark examples.
- `aoa_local_ai_trials.py` is the part-local compatibility bridge for
  `scripts/aoa-local-ai-trials`; the preserved runner lives under
  `../../legacy/trials/artifacts/scripts/aoa-local-ai-trials`.
- `legacy_trial_adapter.py` is the active role-level adapter for callers that
  need the preserved runner's wire IDs without making archived stage names
  current topology again.

The old step-gated runner implementation and narrative remain routed through
`../../legacy/INDEX.md`; keep active part docs in trial, scenario, benchmark,
model-card, and promotion language.

Live benchmark runs remain runtime artifacts under `${AOA_STACK_ROOT}/Logs/`.
