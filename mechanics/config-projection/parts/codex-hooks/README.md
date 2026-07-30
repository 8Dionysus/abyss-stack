# Codex hook composition

This config-projection part merges independently owned Codex command-hook
fragments into one native `hooks.json` candidate.

## Start here

- [CONTRACT](CONTRACT.md)
- [VALIDATION](VALIDATION.md)

## Source surfaces

- `schemas/codex-hooks-fragment.schema.json`
- `schemas/codex-hooks-composition-receipt.schema.json`
- `scripts/render_codex_hooks.py`
- `tests/test_render_codex_hooks.py`

## Function

The renderer accepts repeatable fragments. A fragment may be either:

- a native Codex hook config, such as standalone output produced by
  `aoa-session-memory`; or
- an owner envelope with `schema_version`,
  `fragment_id`, `owner`, `mode`, declared bindings, and native `hooks`.

It validates command-only current Codex shapes, resolves explicitly supplied
safe absolute-path bindings, rejects unresolved placeholders and exact
duplicate handlers, and merges matching event groups in fragment order.
Metadata is removed from the native output.

Read-only rendering is the default. `--check-output` compares an existing
projection without changing it. `--write` is an explicit atomic install route:
it writes mode `0600`, preserves an existing target in a private backup
directory, emits a content-minimized composition receipt, and rolls the target
back if receipt creation fails.

## Boundary

This part owns configuration composition, exact source digests, atomic
projection, backup, and rollback. It does not own hook meaning, event policy,
memory semantics, session evidence, skill selection, Codex trust, live hook
health, or benefit.

`aoa-memo` and `aoa-session-memory` remain independently usable owner
repositories. Either can produce a fragment without importing or invoking the
other. Coexistence happens only at this neutral projection seam.
