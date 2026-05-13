# Runtime Lifecycle Roadmap

## Initial landing

- create this package as the route home
- keep root operator docs in root `docs/` and part-specific docs under owning
  lifecycle parts
- make future lifecycle movement reviewable
- land optional cache/usage status readout schemas, examples, and tests under
  the package

## Next candidates

- decide whether `docs/RUNBOOK.md` stays root-facing or splits into package detail
- map profile and preset docs against compose ownership
- add a lifecycle-specific validator only if root `validate_stack.py` becomes too broad
