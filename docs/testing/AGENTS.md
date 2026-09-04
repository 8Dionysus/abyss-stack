# AGENTS.md

Local guidance for `docs/testing/` in `abyss-stack`. Read root `AGENTS.md`,
`docs/AGENTS.md`, and `tests/AGENTS.md` first.

## Scope

This district owns the human test topology and machine-readable test inventory
for root tests, mechanic part-local tests, MCP service tests, and explicit
archive-review tests.

The machine inventory lives at `docs/testing/test_inventory.json`.

It does not own executable command sequences. Those live in
`docs/validation/validation_lanes.json` and local route cards.

## Contract

- Keep test inventory descriptive: family, paths, owner surface, lane, mode,
  focused target, and failure route.
- Keep legacy paths out of default pytest discovery and default inventory.
- Keep live-host, destructive, private, or model-download behavior out of the
  default source-checkout test lane.
- Add topology tests when a new test home, lane, or runner behavior appears.

## Validate

Validation is on-demand: use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
