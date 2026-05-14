# Diagnostic Spine Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Doctor readiness | `parts/doctor-readiness/` | `scripts/aoa-doctor`, `parts/doctor-readiness/aoa_doctor.sh`, `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`, `mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md` |
| Diagnose wrapper | `parts/diagnose-wrapper/` | `scripts/aoa-diagnose`, `parts/diagnose-wrapper/aoa_diagnose.sh`, `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py` |
| Truth surfaces | `parts/truth-surfaces/` | `mechanics/diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md`, `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md` |
| Diagnostic surfaces | `parts/diagnostic-surfaces/` | `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`, `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_RUNTIME_PACKET.md`, schemas, examples, generated catalog, and package-local tests under `mechanics/diagnostic-spine/parts/diagnostic-surfaces/` |

Keep these parts together: if a diagnostic surface moves or changes, update the
authority docs, catalog generator, validators, and tests in the same pass.
