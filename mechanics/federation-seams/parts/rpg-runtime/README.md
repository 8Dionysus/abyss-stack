# Federation Seam Surfaces

This directory carries package-local, public-safe contracts for runtime
read-model surfaces that consume sibling owner meaning without becoming that
meaning.

## RPG Runtime Projection

- `docs/` defines the runtime route, collection, builder, and frontend
  projection posture.
- `schemas/` defines item and collection contracts for RPG runtime read models.
- `examples/` defines public-safe seed items used by
  `scripts/aoa-rpg-runtime-projection`.
- Generated collections belong in `mechanics/federation-seams/parts/rpg-runtime/generated/`.

Keep root questbook schemas and examples in root `schemas/` and `examples/`
until their mixed quest and repository-contract role has a cleaner owner split.
