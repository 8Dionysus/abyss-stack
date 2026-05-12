# Federation Seam Generated Outputs

Generated outputs here are source-checkout transports for federation-facing
runtime read models. They are lower authority than their schemas, examples,
builders, and upstream owner surfaces.

## RPG

`rpg/` is produced by `scripts/aoa-rpg-runtime-projection` from package-local
schemas and examples under `mechanics/federation-seams/parts/rpg-runtime/`.

Use:

```bash
python scripts/aoa-rpg-runtime-projection --generated-only
python scripts/aoa-rpg-runtime-projection --generated-only --check
```
