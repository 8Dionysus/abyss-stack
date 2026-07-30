# Codex hook composition contract

## Owner boundary

`abyss-stack` owns the neutral projection of already-authored hook definitions
into one native Codex config. Each fragment owner retains the meaning,
authority ceiling, lifecycle, tests, and removal policy of its hook.

The compositor must not:

- reinterpret, synthesize, enable, disable, or reorder owner hook semantics;
- turn a native standalone config into a dependency on another fragment;
- accept prompt or agent handlers while current Codex executes only command
  handlers;
- preserve envelope metadata in the native output;
- silently resolve a placeholder, duplicate a handler, or accept an unsafe
  binding;
- treat a rendered file, composition receipt, or trusted definition as proof
  that a hook ran or helped.

## Inputs

- one or more JSON files supplied explicitly in command-line order;
- zero or more `NAME=/safe/absolute/path` bindings;
- optionally, one existing native output for exact comparison;
- for explicit write only, one target path and one receipt path.

Owner-envelope bindings are complete and exact: declared names must equal
placeholders found in command strings, each declared name must be supplied,
and unused supplied bindings fail closed. Native configs must already be fully
resolved.

## Output

The read-only output is native Codex JSON with only `description` and `hooks`.
Event groups and handlers preserve input order. The composition receipt binds:

- source order, fragment id, owner, mode, and source digest;
- binding names and value digests, never raw binding values;
- output digest and event/group/handler counts;
- hashed target identity, previous-output digest, and backup file name/digest
  when an explicit write changed the target;
- whether the target changed.

The receipt carries no prompt, tool input, tool output, memory content,
transcript content, secret, or semantic claim.

## Write and rollback

`--write` requires `--receipt`. The target parent must already exist. An
existing target must be a regular non-symlink file and is copied byte-for-byte
to a private mode-`0600` backup before replacement. The new native output is
atomically replaced and mode-`0600`. If the receipt cannot be written, the
previous target is restored atomically, or a newly created target is removed.

This source contract does not itself authorize writing `~/.codex/hooks.json`.
Exact Codex trust remains a separate operator-visible gate.
