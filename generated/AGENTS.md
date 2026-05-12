# AGENTS.md

Local guidance for `generated/` in `abyss-stack`. Read the root `AGENTS.md` first.
Generated artifacts are lower authority than their sources.

## Scope

This directory carries compact machine-readable outputs such as runtime kernel
registries. Diagnostic spine generated output now lives under
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/`, including
`diagnostic_surface_catalog.min.json`. RPG runtime read-model outputs now live
under `mechanics/federation-seams/parts/rpg-runtime/generated/`.
They help agents and tools read the runtime quickly, but they are not the place to author new runtime doctrine.

## Local contract

- Do not hand-edit generated JSON when a source, schema, or builder owns the value.
- Regenerate from the owning script or update the generator first, then commit the resulting artifact.
- Keep generated outputs deterministic, public-safe, minified when already minified, and free of live secrets or private host state.
- When the source contract changes, move docs, schemas, examples, tests, and generated artifacts together.

## Change rules

If a generated artifact changes without a source or builder change, explain why it is legitimate. Otherwise treat it as drift.
For diagnostic surfaces, the package-local catalog is checked by the diagnostic
catalog builder and validator.
For RPG runtime projections, the package-local generated outputs are checked by
`scripts/aoa-rpg-runtime-projection --generated-only --check` in source-only
workflows.

## Validate

Common gates:

```bash
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python scripts/aoa-rpg-runtime-projection --generated-only --check
python scripts/validate_stack.py
```
