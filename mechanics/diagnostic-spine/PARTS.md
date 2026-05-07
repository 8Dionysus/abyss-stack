# Diagnostic Spine Parts

| Part | Current source surfaces |
|---|---|
| Doctor readiness | `scripts/aoa-doctor`, `docs/DOCTOR.md`, `docs/LOCAL_OPS_DOCTOR_SPLIT.md` |
| Diagnose wrapper | `scripts/aoa-diagnose`, `scripts/_aoa_diagnose.py` |
| Truth surfaces | `docs/TRUTH_SURFACES.md`, `docs/RENDER_TRUTH.md` |
| Diagnostic contracts | `schemas/diagnostic_*.schema.json`, `schemas/diagnosis_companion.schema.json`, `schemas/repair_handoff.schema.json` |
| Public examples | `examples/diagnostic_*.example.json`, `examples/diagnosis_companion.min.example.json`, `examples/repair_handoff.min.example.json` |
| Generated catalog | `generated/diagnostic_surface_catalog.min.json`, catalog build and validate scripts |
| Tests | `tests/test_aoa_diagnose.py`, diagnostic stack tests |

Do not move these parts until authority refs and validators follow.

