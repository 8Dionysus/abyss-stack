# AGENTS.md

Local guidance for `tests/` in `abyss-stack`. Read the root `AGENTS.md` first.
This directory is the runtime validation gate for infrastructure contracts.

## Scope

Tests here protect repo-level integration behavior: compose rendering,
public-safe templates, env examples, source/runtime parity, route cards, and
root validators. Package-owned mechanics tests live under the owning
`mechanics/<name>/parts/<part>/tests/` directory.
They should prove the source checkout contract without requiring a live deployed host.

## Local contract

- Keep `tests/README.md` as the short index for repo-level tests.
- Keep tests deterministic and public-safe.
- Prefer fixtures, temp directories, stub inputs, and loopback assumptions over live services.
- Keep no live host state dependencies: no private `/srv/AbyssOS/abyss-stack` captures, real secrets, local model downloads, or workstation-specific paths.
- When schemas, generated catalogs, config templates, or runtime helper scripts change, add the nearest targeted regression test.
- When adding or moving root, mechanic, MCP, or legacy-provenance tests, update
  `docs/testing/test_inventory.json`.
- When changing validation lane commands or script/validator topology, update
  `docs/validation/` and the focused topology tests.
- Keep destructive behavior behind dry-run or explicit fake fixtures.

## Validate

Use targeted tests first, then broaden only when needed:

```bash
python -m pytest
python scripts/ci_gate.py --mode tests
python scripts/validate_stack.py
```
