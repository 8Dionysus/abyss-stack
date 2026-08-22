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
- `scripts/codex_pretool_agent_routing.py`
- `config/abyss-stack-agent-tool-routing.fragment.json`
- `tests/test_render_codex_hooks.py`
- `tests/test_codex_pretool_agent_routing.py`

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

The stack-owned `abyss-stack:agent-tool-routing:v1` fragment adds the current
Codex `PreToolUse` command adapter for the `collaboration*` tool namespace. The
adapter recognizes the Codex wire names, reads only an explicitly supplied
typed context file (`AOA_AGENT_TOOL_ROUTING_CONTEXT_FILE`), and asks
`aoa-sdk.ControlPlaneAPI.pre_tool_route()` for the typed next-owner posture.
It reflects that posture as a native allow or deny. `aoa-agents` remains the
owner of responsibility classification and role-first meaning; this adapter
does not choose a role, model, runtime, workspace, or actor and never copies
opaque `tool_input` into its output.

Each valid context file is claimed by an atomic rename and immediately
unlinked before the SDK route, making the classification single-use for one
collaboration attempt without retaining its Goal/holder metadata. When
`AOA_SDK_SOURCE_ROOT` is supplied, the adapter checks both the package presence
and the source location of the imported SDK modules. The fragment gives the
adapter a ten-second native Codex timeout, while the adapter emits a deny after
its five-second inner route bound so a stalled SDK path cannot fall through as
an unblocked hook timeout.

Missing or malformed typed context fails closed for a recognized collaboration
tool without inventing Goal or holder identity. A classified
`not_independent` result is the only posture that permits the Codex-local
compatibility path. The context schema and its producer remain outside this
neutral compositor.

Read-only rendering is the default. `--check-output` compares an existing
projection without changing it. `--write` is an explicit atomic install route:
it writes mode `0600`, preserves an existing target in a private backup
directory, emits a content-minimized composition receipt, and rolls the target
back if receipt creation fails.

## Boundary

This part owns configuration composition, exact source digests, atomic
projection, backup, and rollback. It does not own hook meaning, event policy,
memory semantics, session evidence, skill selection, Codex trust, live hook
health, or benefit. The adapter's wire projection is stack-owned, while the SDK
route decision and owner classification remain outside this part's authority.

`aoa-memo` and `aoa-session-memory` remain independently usable owner
repositories. Either can produce a fragment without importing or invoking the
other. Coexistence happens only at this neutral projection seam.
