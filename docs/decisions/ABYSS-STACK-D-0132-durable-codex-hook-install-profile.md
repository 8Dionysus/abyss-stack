# Durable Codex Hook Install Profile

- Decision ID: ABYSS-STACK-D-0132
- Status: accepted
- Date: 2026-08-22
- Owner surface: `mechanics/config-projection/parts/codex-hooks/`

## Index Metadata

- Original date: 2026-08-22
- Surface classes: Codex hooks, config projection, runtime install, rollback
- Stack lanes: source, runtime, operator
- Mechanic parents: config-projection
- Guard families: source identity, content-addressed release, atomic hook composition
- Posture: accepted durable install route; trust and live proof remain separate

## Context

The first landed Codex `PreToolUse` adapter was source-correct but its active
profile pointed at a task-local merged worktree and a proof-only context
directory. That made the source/installation boundary non-durable for an
ordinary fresh Codex session. The adapter also needs an attempt-keyed context,
but the current Codex payload does not author the typed Goal/current-holder
base required by `aoa-sdk`.

## Options considered

- Keep the active command pointed at whichever source or proof worktree last
  installed it.
- Copy the adapter into one mutable global directory without a source digest or
  rollback record.
- Make the stack choose Goal, holder, role, or classification meaning in the
  hook so no external context is required.
- Materialize an exact clean-source release, compose it with the native hook
  set atomically, and use a narrow wire relay for a session-owned typed base.

## Decision

Add a stack-owned durable install profile under the deployed runtime's isolated
`.codex-home/agent-tool-routing/` root. The package-local installer requires a
clean exact `abyss-stack` commit, copies an allowlisted set of hook sources and
fragments into a content-addressed release, verifies manifest closure, and
uses the existing renderer to compose native hooks, the transport relay, and
the adapter with a private backup and receipt. If the installer receipt cannot
be committed, the prior target bytes and mode are restored.

The relay accepts only a typed base supplied through the session/owner
`AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE` environment path. It copies only
`session_id`, `turn_id`, `tool_use_id`, and `tool_name` from the current
`PreToolUse` event into the event-keyed single-use context. It does not author
the base, route the request, classify responsibility, or select a role/model/
runtime/actor. The active command therefore contains only stable runtime
release, context-directory, and SDK-source coordinates.

## Rationale

An immutable release gives the active Codex profile a stable executable/source
identity while retaining the renderer's existing native-hook preservation and
rollback contract. A clean source requirement prevents an unreviewed dirty
worktree from becoming an installed runtime. Keeping the relay separate from
the adapter preserves the owner split: `abyss-stack` owns the Codex wire and
projection, `aoa-sdk` owns typed next-owner routing, and `aoa-agents` owns
responsibility classification and role-first meaning.

## Consequences

- The active hook no longer depends on a task-local worktree or proof root.
- Reinstalling the same clean source commit reuses a verified release; a new
  source commit creates a new release and leaves the predecessor available for
  rollback.
- A session owner must publish a truthful typed base before a recognized
  agent-tool call can proceed; missing base remains fail-closed.
- Install, Codex trust, fresh-session execution, SDK routing, classification,
  actor launch, and Goal acceptance remain separate evidence claims.

## Source surfaces

- `mechanics/config-projection/parts/codex-hooks/`
- `docs/runtime/PATHS.md`
- `docs/runtime/STORAGE_LAYOUT.md`
- `docs/install/DEPLOYMENT.md`
- `docs/decisions/ABYSS-STACK-D-0131-codex-pretool-agent-routing-adapter.md`

## Follow-up route

The session/owner route that publishes `AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE`
must provide the current typed context under its own authority. Route SDK
routing changes to `aoa-sdk`, responsibility and role-first changes to
`aoa-agents`, Codex trust to the operator/client boundary, and live causal
proof or Goal acceptance to their respective owners.
