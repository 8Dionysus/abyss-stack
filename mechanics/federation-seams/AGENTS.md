# AGENTS.md

Applies to `mechanics/federation-seams/`.

This package owns the route shape for runtime consumption of sibling owner
surfaces, advisory mirrors, route-api posture, and federation sync checks.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`, and
`PARTS.md` before editing.

Do not treat mirrored owner surfaces as abyss-stack-authored truth. Do not make
federation mandatory unless the owning profiles and runtime checks move too.

Validation:

```bash
python scripts/validate_stack.py
bash -n scripts/aoa-sync-federation-surfaces scripts/aoa-federated-check
```

