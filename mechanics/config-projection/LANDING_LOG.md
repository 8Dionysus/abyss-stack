# Config Projection Landing Log

## 2026-05-07 - First-wave package landing

Created the config projection package as a route home for templates, env
examples, bootstrap, render, and sync surfaces.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Part-local docs topology

Moved bootstrap and render-truth docs into `parts/bootstrap/docs/` and
`parts/rendering/docs/`. Package `docs/README.md` now stays as a route index.

Validation route: `python scripts/validate_stack.py`.
