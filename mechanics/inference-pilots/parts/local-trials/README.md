# Inference Pilot Surface Contracts

This directory keeps inference-pilot machine-readable benchmark surfaces
package-local.

- `docs/LOCAL_AI_TRIALS.md` owns the local trial route narrative.
- `docs/RUNTIME_BENCH_POLICY.md` owns benchmark evidence posture.
- `schemas/` defines runtime benchmark manifest contracts.
- `examples/` carries public-safe benchmark examples.
- `aoa_local_ai_trials.py` is the part-local compatibility bridge for
  `scripts/aoa-local-ai-trials`; the active runner lives under
  `compatibility-runners/aoa-local-ai-trials`.
- `trial_compatibility_bridge.py` is the active role-level bridge for callers
  that need the preserved runner's wire IDs without making archived stage names
  current topology again.

The archive remains provenance under `../../legacy/`; active wrappers and
validators route through package-local runner files.

Live benchmark runs remain runtime artifacts under `${AOA_STACK_ROOT}/Logs/`.
