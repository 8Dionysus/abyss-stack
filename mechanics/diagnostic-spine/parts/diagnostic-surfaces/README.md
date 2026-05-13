# Diagnostic Surface Contracts

This directory keeps the diagnostic spine machine-readable surfaces package-local.

- `docs/DIAGNOSTIC_SPINE.md` owns the diagnostic surface authority posture.
- `schemas/` defines the public diagnostic JSON Schema contracts.
- `examples/` provides public-safe minimal examples for those contracts.

The generated catalog in `mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/` is rebuilt from
these paths by `scripts/build_diagnostic_surface_catalog.py`.
