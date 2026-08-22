# Codex hook composition

This config-projection part merges independently owned Codex command-hook
fragments into one native `hooks.json` candidate.

## Start here

- [CONTRACT](CONTRACT.md)
- [VALIDATION](VALIDATION.md)

## Source surfaces

- `schemas/codex-hooks-fragment.schema.json`
- `schemas/codex-hooks-composition-receipt.schema.json`
- `schemas/codex-pretool-agent-routing-context.schema.json`
- `scripts/render_codex_hooks.py`
- `scripts/install_codex_hooks.py`
- `scripts/codex_pretool_agent_routing.py`
- `scripts/codex_pretool_agent_routing_context.py`
- `config/abyss-stack-agent-tool-routing.fragment.json`
- `config/abyss-stack-agent-tool-routing-context.fragment.json`
- `tests/test_render_codex_hooks.py`
- `tests/test_codex_pretool_agent_routing.py`
- `tests/test_codex_pretool_agent_routing_context.py`

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

The stack-owned `abyss-stack:agent-tool-routing-context-relay:v1` fragment runs
immediately before the adapter for the canonical `spawn_agent`, known
unnamespaced v2 names, and the `multi_agent_`/`collaboration` namespaces. The
fragment matcher remains broad so future namespace members reach the adapter's
unknown-agent denial, but the relay writes context only for the current
recognized names; an unknown member therefore leaves no unclaimable entry.
The relay reads a session-owned typed base from the inherited
`AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE` path and copies only the current safe
attempt coordinates into the event-keyed context directory. It never chooses
or interprets Goal, holder, role, model, runtime, or classification meaning.
The `abyss-stack:agent-tool-routing:v1` fragment then adds the current Codex
`PreToolUse` command adapter. The namespace matcher deliberately sends future
names to the adapter's unknown agent-tool denial branch. The composed commands
bind an explicit typed context directory and `aoa-sdk` source root; the adapter
uses the hook event's `cwd` as the workspace coordinate. It reads at most the
configured context limit plus one byte from that directory
(`AOA_AGENT_TOOL_ROUTING_CONTEXT_DIR`), selects the file keyed by the current
event's safe session/turn/tool-use/tool-name identity, verifies the context's
identity against that event, and asks
`aoa-sdk.ControlPlaneAPI.pre_tool_route()` for the typed next-owner posture.
It reflects that posture as a native allow or deny. `aoa-agents` remains the
owner of responsibility classification and role-first meaning; this adapter
does not choose a role, model, runtime, workspace, or actor and never copies
opaque `tool_input` into its output.

The producer writes one exact file per attempt under the directory, named
`attempt-<sha256(canonical safe attempt identity)>.json`. The adapter claims
only that event-keyed directory entry by atomic rename before reading it, then
immediately unlinks the claimed path after validation and before the SDK route.
This makes the classification single-use for one agent-tool attempt without
retaining its Goal/holder metadata; a different concurrent attempt has a
different key and cannot consume it. When
`AOA_SDK_SOURCE_ROOT` is supplied, the adapter checks both the package presence
and the source location of the imported SDK modules. The fragment gives the
adapter a ten-second native Codex timeout, while the adapter emits a deny after
its five-second inner route bound so a stalled SDK path cannot fall through as
an unblocked hook timeout.

Missing or malformed typed context fails closed for a recognized collaboration
tool without inventing Goal or holder identity. A classified
`not_independent` result is the only posture that permits the Codex-local
compatibility path. The context schema and its typed base producer remain
outside this neutral compositor. The relay is only a stack-owned wire
transport for a base published by the session/owner route.

`install_codex_hooks.py` is the explicit operator install route. It requires a
clean exact `abyss-stack` commit, materializes the hook scripts and fragments
under an immutable content-addressed release below the deployed
`.codex-home/agent-tool-routing/` root, and composes the supplied native hook
fragment with relay then adapter through the renderer. It records source,
release, composition, target, and rollback digests without embedding the
session base or any Goal/task identity in the active command. The release is
reused only after its manifest closure and file digests verify.

Read-only rendering is the default. `--check-output` compares an existing
projection without changing it. `--write` is an explicit atomic install route:
it writes mode `0600`, preserves an existing target in a private backup
directory, emits a content-minimized composition receipt, and rolls the target
back if receipt creation fails.

## Boundary

This part owns configuration composition, exact source/release digests, atomic
projection, backup, rollback, and the context relay's safe event-coordinate
transport. It does not own the typed base, hook meaning, event policy, memory
semantics, session evidence, skill selection, Codex trust, live hook health, or
benefit. The adapter and relay are stack-owned wire projections, while the SDK
route decision and owner classification remain outside this part's authority.

`aoa-memo` and `aoa-session-memory` remain independently usable owner
repositories. Either can produce a fragment without importing or invoking the
other. Coexistence happens only at this neutral projection seam.
