# reference-platform

This directory owns the machine-readable public reference-platform layer for `abyss-stack`.

## Files

- `schema.v1.json` defines the v1 host-facts contract.
- `reference-host.public.json.example` shows the intended public-safe shape.
- `reference-host.public.json` is the reviewed canonical Linux reference-host snapshot when one has been intentionally selected and refreshed.

## Rules

- keep this directory public-safe
- keep the repository on schema plus example until the canonical Linux reference host is explicitly selected
- once selected, refresh `reference-host.public.json` intentionally rather than treating it as a routine local capture
- do not store private host captures here
- private captures belong under `${AOA_STACK_ROOT}/Logs/host-facts/`
- when the schema changes, update `docs/REFERENCE_PLATFORM_SPEC.md`, `scripts/aoa-host-facts`, validation, and workflow coverage in the same change
