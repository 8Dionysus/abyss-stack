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

The stack-owned context relay is a transport exception with a narrow ceiling:
it may copy the current event's four safe attempt coordinates into a
single-use entry, but it may not author or alter the typed base. The base must
be supplied by the current session/owner route through
`AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE`.

## Inputs

- one or more JSON files supplied explicitly in command-line order;
- zero or more `NAME=/safe/absolute/path` bindings;
- optionally, one existing native output for exact comparison;
- for explicit write only, one target path and one receipt path.

The durable installer additionally requires one clean exact source checkout,
one native fragment path, one `aoa-sdk` source root, an install root, a context
directory, and explicit renderer receipt/backup paths. It copies only the
allowlisted hook source files into a content-addressed release and refuses a
dirty or symlinked source/release input. The release is finalized read-only;
target, active receipt, composition receipt, and each per-install receipt are
distinct path identities, and receipt creation uses exclusive reservation.

Owner-envelope bindings are complete and exact: declared names must equal
placeholders found in command strings, each declared name must be supplied,
and unused supplied bindings fail closed. Native configs must already be fully
resolved.

The stack-owned agent-routing fragment is a Codex-wire projection, not a
responsibility owner. Its `PreToolUse` matcher covers the canonical
`spawn_agent`, known v2 unnamespaced names, and any identity in the
`multi_agent_` or `collaboration` namespaces so future namespace members reach
the adapter's unknown-agent fail-closed branch. The relay fragment uses the
same broad matcher but materializes a context only for the explicit recognized
name set; an unknown namespace member reaches the adapter without leaving a
stale context file. It invokes the adapter with explicit safe bindings for the
context directory and selected `aoa-sdk` source root. The workspace remains the
current hook event's `cwd`; the adapter does not select a workspace. The
adapter must receive an exact typed context
directory through `AOA_AGENT_TOOL_ROUTING_CONTEXT_DIR`; it does not invent Goal
or current-holder identity from a missing payload and does not copy opaque Codex
`tool_input` into the hook response. The producer stores each context as
`attempt-<sha256(canonical safe attempt identity)>.json`, where the identity is
the current `session_id`, `turn_id`, `tool_use_id`, and `tool_name`. The adapter
selects only that event-keyed file and rejects a context whose identity does not
equal the current event. It reads at most the configured context limit plus one
byte before rejecting an oversized file. The selected directory entry is
atomically claimed before the adapter reads it, and the claimed path is
immediately unlinked after validation and before the SDK call. A stale or
cross-call classification therefore cannot be reused for a later agent-tool
attempt, and a different concurrent attempt cannot consume the selected file.
If `AOA_SDK_SOURCE_ROOT` is supplied, the adapter requires its
`src/aoa_sdk` package and verifies that the imported SDK modules remain beneath
that source root. It presents the typed intent to `aoa-sdk`, reflects only the
SDK decision, and leaves responsibility classification and role-first dispatch
to `aoa-agents`. The native hook timeout is longer than the adapter's bounded
inner route timeout; an inner timeout emits a deny response before Codex can
time out the hook itself.

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
The installer rejects aliases among the target, active receipt, composition
receipt, and per-install receipt before composition. It also restores the
previous composition receipt and removes the reserved per-install receipt when
a later receipt write fails.

This source contract does not itself authorize writing `~/.codex/hooks.json`.
Exact Codex trust remains a separate operator-visible gate. The installer does
not authorize Codex trust, live health, owner classification, external actor
launch, or Goal acceptance. If the install receipt cannot be written, it
restores the previous target bytes and mode after the renderer's own rollback
boundary.
