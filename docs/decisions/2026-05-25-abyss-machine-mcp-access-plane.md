# Abyss Machine MCP Access Plane

Status: accepted
Date: 2026-05-25

## Context

Agents repeatedly need a compact, typed, owner-aware view of the local machine:
what is true now, what constrains action, what is safe to do next, where the
evidence lives, and which layer owns the truth.

`abyss-machine` already owns the host read models and bridge contracts.
`abyss-stack` already owns MCP access-plane packaging. Without a stack-owned MCP
adapter, agents must rediscover host context through ad hoc shell reads and
large bridge payloads.

## Options considered

1. Keep machine access as direct shell reads of `abyss-machine`.
2. Implement a broad MCP control plane that can run arbitrary host commands.
3. Add a stack-owned, stdio-only, read-only MCP adapter over allowlisted
   `abyss-machine ... --json` read models.

## Decision

Choose option 3.

Add `mcp/services/abyss-machine-mcp/` as the stack-owned runnable MCP package
for the stable Codex server name `abyss_machine`.

The service exposes compact resources, tools, and prompts for machine briefs,
owner boundaries, evidence maps, selected safe read surfaces, focused nervous
recall, and non-mutating route preflight. It reads only allowlisted
`abyss-machine ... --json` commands.

## Rationale

This preserves the owner split. `abyss-machine` remains the host authority.
`abyss-stack` owns the service package and stdio topology. MCP becomes a
structured access plane rather than a second machine owner or a generic command
executor.

The route also keeps prompts small: agents can obtain the machine map, evidence
refs, protected roots, mutation gates, and safe-next-route hints without loading
the entire host bridge archive into context.

## Consequences

- Agents can ask `abyss_machine` for the current compact machine map.
- Host evidence refs and truth owners stay visible in every response.
- The service stays stdio-only and read-only.
- Route planning remains preflight-only and does not launch, repair, restart,
  clean, kill, throttle, or approve mutation.
- Future non-stdio exposure, write tools, privileged commands, repair tools,
  service lifecycle control, process mutation, private raw capture access,
  memory landing, or proof publication require a new decision.

## Source surfaces

- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `mcp/services/abyss-machine-mcp/AGENTS.md`
- `mcp/services/abyss-machine-mcp/DESIGN.md`
- `mcp/services/abyss-machine-mcp/README.md`
- `mcp/services/abyss-machine-mcp/src/abyss_machine_mcp/core.py`
- `/etc/abyss-machine/AGENTS.md`
- `/etc/abyss-machine/DESIGN.md`

## Follow-up route

Run the service-local validation, stack validation, and Codex-plane smoke after
the shared-root renderer wires `abyss_machine`.
