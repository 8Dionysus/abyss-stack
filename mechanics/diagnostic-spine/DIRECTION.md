# Diagnostic Spine Direction

This package keeps runtime diagnosis read-only, source-backed, and repair-safe.

Current posture:

- keep doctor readiness separate from diagnosis bundles
- keep diagnostic schemas, examples, generated catalogs, and tests under the
  owning diagnostic-surfaces part
- keep handoff candidates as evidence for later review, not completed repair
- keep truth-goal language bounded to source-checkable runtime claims

Near direction:

- keep generated diagnostic catalogs rebuilt from source
- keep repair handoff vocabulary aligned with runtime-repair without merging
  the two mechanics
- add narrow tests when new diagnostic surfaces or truth-goal fields appear
- route host-specific gaps through machine-fit instead of encoding private host
  facts into public docs
