# AGENTS.md

Applies to `mechanics/federation-seams/`.

This package owns the route shape for runtime consumption of sibling owner
surfaces, advisory mirrors, route-api posture, and federation sync checks.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not treat mirrored owner surfaces as abyss-stack-authored truth. Do not make
federation mandatory unless the owning profiles and runtime checks move too.
Upstream names that must remain for route-api or mirror compatibility belong in
`parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`; active local docs
should use the clean runtime aliases.

Validation:

```bash
python scripts/validate_stack.py
scripts/aoa-rpg-runtime-projection --generated-only --check
python -m pytest mechanics/federation-seams/parts/rpg-runtime/tests/test_rpg_runtime_projection.py -q
python -m py_compile mechanics/federation-seams/parts/federation-checks/aoa_federated_check.py mechanics/federation-seams/parts/rpg-runtime/aoa_rpg_runtime_projection.py
bash -n scripts/aoa-sync-federation-surfaces mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh
```
