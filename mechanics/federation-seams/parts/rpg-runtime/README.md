# Federation Seam Surfaces

This directory carries package-local, public-safe contracts for runtime
read-model surfaces that consume sibling owner meaning without becoming that
meaning.

## RPG Runtime Projection

- `docs/` defines the runtime route, collection, builder, and frontend
  projection posture, including the runtime materialization packet.
- `schemas/` defines item and collection contracts for RPG runtime read models.
- `examples/` defines public-safe fixture items used by
  `scripts/aoa-rpg-runtime-projection`.
- `aoa_rpg_runtime_projection.py` is the part-local backend for the root
  wrapper.
- Generated collections belong in `mechanics/federation-seams/parts/rpg-runtime/generated/`.

The generated runtime projection may point to Dionysus prep-pack routes through
the upstream compatibility bridge because `Dionysus` currently owns seed garden
and staging lineage. That path is an owner handoff route, not an `abyss-stack`
active topology name.

Keep root questbook schemas and examples in root `schemas/` and `examples/`
until their mixed quest and repository-contract role has a cleaner owner split.
