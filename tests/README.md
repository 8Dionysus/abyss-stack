# tests

`tests/` contains repository-level validation tests for `abyss-stack`.

Package-owned mechanic tests live under their owning
`mechanics/<package>/parts/<part>/tests/` routes. Root tests should stay focused
on integration contracts that span the repository: validators, source/runtime
parity, questbook shape, route cards, public-safe templates, and release-facing
roadmap checks.

## Current Test Surface

- `test_validate_stack_required_files.py`: required source files and portable
  mirror hygiene guards.
- `test_validate_stack_parity.py`: source/deployed parity behavior.
- `test_validate_stack_questbook.py`: questbook schemas, examples, and RPG
  runtime routes.
- `test_validate_stack_federation.py`: federation template requirements.
- `test_validate_nested_agents.py`: nested AGENTS coverage.
- `test_roadmap_parity.py`: release-contour route parity.
- `test_current_direction_routes.py`: root entrypoint direction.
- `test_aoa_lib_env_compat.py`: shared shell env compatibility.

See [AGENTS.md](AGENTS.md) for editing rules.
