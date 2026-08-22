# Codex PreToolUse Agent-Routing Adapter

- Decision ID: ABYSS-STACK-D-0131
- Status: accepted
- Date: 2026-08-21
- Owner surface: `mechanics/config-projection/parts/codex-hooks/`

## Index Metadata

- Original date: 2026-08-21
- Surface classes: Codex hooks, config projection, owner boundary
- Stack lanes: source, runtime, operator
- Mechanic parents: config-projection, governed-execution
- Guard families: pre-execution routing, fail-closed identity, fragment preservation
- Posture: accepted typed wire adapter; live activation remains separately verified

## Context

Codex 0.148.0 exposes built-in collaboration tools through the native
`PreToolUse` hook payload. The SDK already owns the typed responsibility route,
and `aoa-agents` owns classification and role-first dispatch, but no stack-owned
wire adapter presented the actual built-in attempt to that route before Codex
execution. The payload does not itself provide the parent Goal and current
holder references required by the SDK contract.

## Options considered

- Let the native Codex tool execute and rely on prompt guidance.
- Put role, model, runtime, or actor selection into a Codex hook.
- Add a universal hook that invents identity when the payload is incomplete.
- Add a narrow stack-owned wire adapter with an explicit typed context boundary.

## Decision

Add a command-only `PreToolUse` fragment for the known Codex
`collaboration*` tool namespace. The adapter reads the event identity and
opaque-tool presence, obtains the current Goal/holder and route state only from
an exact externally supplied context file, constructs
`aoa_agent_tool_routing_intent_v1`, and calls `aoa-sdk.ControlPlaneAPI`.

The adapter denies unresolved and independent routes with actionable
`aoa-agents-skills` role-first direction. It permits the built-in local
compatibility path only for a typed `not_independent` SDK posture. Missing or
malformed context, unknown collaboration names, and unsupported SDK postures
fail closed. A valid context is atomically claimed and immediately unlinked
before the SDK call, so a classification cannot be reused for a later
collaboration attempt while successful calls retain no context metadata. When an
explicit SDK source root is supplied, the adapter verifies both package
presence and imported module provenance. Its inner route timeout emits a deny
before the longer native hook timeout. Unrelated tools pass through unchanged.
The adapter does not choose a role, model, runtime, workspace, or actor, and
the compositor does not own the context producer, classification, trust, or
live health.

## Rationale

The stack is the owner of the Codex configuration and wire projection, while
the SDK and `aoa-agents` retain their existing typed authority. An explicit
context boundary is necessary because the current Codex payload cannot prove
the parent identity. Failing closed prevents a convenient built-in call from
silently bypassing the route and keeps raw tool arguments out of the adapter's
response.

## Consequences

- The real built-in attempt can be blocked before execution when the installed
  fragment and typed context are present.
- Existing native session, memo, and other owner fragments remain composable in
  the same projection.
- Source composition, installation, Codex trust, hook execution, owner
  classification, actor launch, and Goal acceptance remain separate claims.
- A context producer and fresh model-visible live proof are required before
  claiming an active end-to-end route.

## Source surfaces

- `mechanics/config-projection/parts/codex-hooks/`
- `mechanics/config-projection/PARTS.md`
- `mechanics/config-projection/PROVENANCE.md`
- `docs/decisions/ABYSS-STACK-D-0103-compose-independent-codex-hook-fragments.md`
- `aoa-sdk` decision `AOA-SDK-D-0100-pre-tool-agent-routing-owner`
- `aoa-agents` decision `AOA-AG-D-0069-pre-tool-agent-delegation-intercept`

## Follow-up route

Install the merged fragment through the existing explicit config-projection
route, preserve the current native hook set and trust posture, and collect a
fresh Codex session showing hook execution and a causal built-in tool block.
Route context-producer or classification changes to `aoa-sdk` or `aoa-agents`
respectively; route semantic proof and acceptance to the parent Goal owner.
