# Diagnostic Spine Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Doctor readiness | `parts/doctor-readiness/` | `scripts/aoa-doctor`, `docs/DOCTOR.md`, `docs/LOCAL_OPS_DOCTOR_SPLIT.md` |
| Diagnose wrapper | `parts/diagnose-wrapper/` | `scripts/aoa-diagnose`, `scripts/_aoa_diagnose.py` |
| Truth surfaces | `parts/truth-surfaces/` | `docs/TRUTH_SURFACES.md`, `docs/RENDER_TRUTH.md` |
| Diagnostic surfaces | `parts/diagnostic-surfaces/` | schemas, examples, generated catalog, and package-local tests under `mechanics/diagnostic-spine/parts/diagnostic-surfaces/` |

Keep these parts together: if a diagnostic surface moves or changes, update the
authority docs, catalog generator, validators, and tests in the same pass.
