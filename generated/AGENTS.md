# AGENTS.md

Local guidance for `generated/` in `abyss-stack`. Read the root `AGENTS.md` first.
Generated artifacts are lower authority than their sources.

## Scope

This directory carries compact machine-readable outputs such as `diagnostic_surface_catalog.min.json`, runtime kernel registries, and RPG-side generated projections.
They help agents and tools read the runtime quickly, but they are not the place to author new runtime doctrine.

## Local contract

- Do not hand-edit generated JSON when a source, schema, or builder owns the value.
- Regenerate from the owning script or update the generator first, then commit the resulting artifact.
- Keep generated outputs deterministic, public-safe, minified when already minified, and free of live secrets or private host state.
- When the source contract changes, move docs, schemas, examples, tests, and generated artifacts together.

## Change rules

If a generated artifact changes without a source or builder change, explain why it is legitimate. Otherwise treat it as drift.
For diagnostic surfaces, `diagnostic_surface_catalog.min.json` is checked by the diagnostic catalog builder and validator.

## Validate

Common gates:

```bash
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python scripts/validate_stack.py
```
