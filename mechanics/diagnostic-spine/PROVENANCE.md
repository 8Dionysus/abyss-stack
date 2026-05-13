# Diagnostic Spine Provenance

This package descends from the doctor, diagnose, truth-surface, and diagnostic
contract files that used to rely on root docs and scripts for most routing.

The refactor pattern is:

- keep `scripts/aoa-doctor` and `scripts/aoa-diagnose` as stable wrappers
- keep readiness and diagnosis implementation bodies under package parts
- keep diagnostic contracts, examples, generated catalog, and focused tests
  under `parts/diagnostic-surfaces/`
- keep generated companions useful but subordinate to their source docs and
  builders

## Owner Boundary

`abyss-stack` owns runtime read models, readiness posture, diagnostic contract
shape, and public-safe handoff candidates. Actual repair belongs to
runtime-repair, operator action, `aoa-skills`, and affected owner repositories.
Private machine facts stay outside the public source mirror.

## Current Bridges

- [PARTS.md](PARTS.md) maps readiness, diagnosis, truth surfaces, and
  diagnostic contracts to package parts.
- [parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md](parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md)
  owns the active diagnostic contract.
- [parts/doctor-readiness/docs/DOCTOR.md](parts/doctor-readiness/docs/DOCTOR.md)
  owns doctor readiness posture.
- [../runtime-repair/README.md](../runtime-repair/README.md) owns repair-safe
  follow-through.
- [../machine-fit/README.md](../machine-fit/README.md) owns host-specific fit
  evidence.
