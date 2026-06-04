# AGENTS.md

Local guidance for `docs/validation/` in `abyss-stack`. Read the root
`AGENTS.md` and `docs/AGENTS.md` first.

## Scope

This district owns validation topology, command authority, validator inventory,
script inventory, and lane manifest documentation for the source checkout.

It does not own runtime doctrine, live host state, sibling repository truth, or
mechanic-local command meaning.

## Contract

- Keep executable lane sequences in `validation_lanes.json`.
- Keep inventories descriptive. They map surfaces to owners, lanes, side
  effects, tests, and failure routes; they do not execute commands.
- Keep root validation entrypoints compatible while implementation bodies move
  only when an owner surface is clear.
- Keep script-side effects explicit, especially for operator wrappers synced
  into deployed `Configs/scripts/`.
- Keep advisory, legacy, live, and provenance surfaces labeled instead of
  letting default discovery silently promote them.

## Validate

```bash
python -m pytest -q tests/test_validation_command_authority.py tests/test_validation_topology.py tests/test_script_topology.py
python scripts/ci_gate.py --mode source-fast
```
