# AGENTS.md

Applies to `mechanics/config-projection/`.

This package owns the route shape for public-safe templates, env examples,
rendering, bootstrap, sync, and deployed `Configs` projection.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `parts/README.md` before editing.

Do not commit live secrets, rendered private config, or machine-local values.
Do not hand-edit deployed `Configs` as source truth.

Validation:

```bash
python scripts/validate_stack.py
bash -n scripts/aoa-bootstrap-configs scripts/aoa-sync-configs scripts/aoa-render-config scripts/aoa-render-services
```
