# Modern-Only MCP Organ Runtime

- Decision ID: ABYSS-STACK-D-0108
- Status: accepted
- Date: 2026-08-09
- Owner surface: `mcp/services/_shared/modern_runtime.py`

## Index Metadata

- Original date: 2026-08-09
- Surface classes: MCP access plane, runtime protocol, consumer compatibility
- Stack lanes: MCP services, runtime lifecycle, organ access fabric
- Mechanic parents: runtime-lifecycle
- Guard families: fail closed, exact identity, protocol version, rollback
- Posture: accepted production protocol cutover

## Context

The active organ fleet was still served by Python MCP 1.27.2 and negotiated
`2025-11-25`.  The current MCP server SDK, the bounded Codex consumer
derivative, and the OS Abyss Tasks extension can use `2026-07-28`, but the
upstream Python server remains dual-era by default.  Merely upgrading the
dependency would therefore leave an undocumented legacy negotiation path and
would not prove that every standalone organ package, candidate contour, or
Codex registration had moved together.

## Options considered

- Keep `2025-11-25` in production and restrict `2026-07-28` to the protocol
  laboratory.
- Upgrade the SDK but continue accepting both old and new protocol versions.
- Move every stack-owned organ adapter to one exact MCP 2.0 runtime seam,
  reject non-`2026-07-28` HTTP requests before session creation, and admit the
  new wire only through exact source, package, consumer, canary, and rollback
  evidence.

## Decision

Choose the third option.  All stack-owned standalone organ MCP packages use
the generated `AbyssMCPServer` seam backed by exact `mcp==2.0.0` and
`mcp-types==2.0.0`.  Streamable HTTP accepts only the exact
`MCP-Protocol-Version: 2026-07-28` header; an older or absent protocol version
is rejected before an MCP session is created.  Read and candidate systemd
contours use the same source-and-lock-addressed Python runtime.

Codex selects `2026-07-28` only for an explicit OS Abyss server-name allowlist
and keeps unrelated external MCP registrations outside this decision.  The
stack-owned read contour may expose the bounded Tasks extension, but Tasks
remain opt-in, principal-bound, durable, cancellable, and read-only; this
decision grants no candidate or effect authority.

Production publication remains subordinate to registry-v2 CAS admission.  A
new deployment invalidates prior canaries and runtime identities, so fail-closed
preflight must block until exact modern-wire evidence is refreshed.  Rollback
restores the preserved prior source projection and MCP 1.27.2 runtime as one
coherent pair; mixed-era source/runtime states are not supported.

## Rationale

One exact server seam prevents fifteen packages from drifting independently,
while explicit rejection removes the false assurance of an upgraded SDK that
still silently negotiates legacy.  An allowlisted consumer migration contains
the Codex experiment to OS Abyss-owned servers.  Reusing the existing
registry-v2, signed-canary, deployment-manifest, and rollback gates preserves
the owner boundaries established by D-0087 and D-0107 instead of creating a
protocol-specific bypass.

## Consequences

- Positive: active stack-owned MCP listeners have one auditable wire version
  and one dependency closure, and future organ packages inherit the same seam.
- Positive: Codex and `abyss-stack-mcp` can exercise the bounded Tasks
  lifecycle without weakening ordinary tool authorization.
- Tradeoff: an old client receives a hard protocol error instead of a fallback,
  and every deployment requires fresh exact canary and registry evidence.
- Tradeoff: external MCP owners such as Chromium or hosted documentation are
  not claimed as migrated by this stack-owned decision.
- Follow-up: remove the bounded Codex derivative only after an upstream stable
  Codex release provides the same per-server `2026-07-28` and Tasks behavior.

## Source surfaces

- `mcp/services/_shared/modern_runtime.py`
- `mcp/services/_shared/build_modern_runtime_vendors.py`
- `mcp/services/_shared/codex_http_client.sh`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/tasks_extension.py`
- `mcp/protocol-lab/`
- `systemd/user/aoa-organ-mcp-read@.service`
- `systemd/user/aoa-memo-mcp-candidate.service`
- `systemd/user/aoa-evals-mcp-candidate.service`
- `systemd/user/abyss-stack-mcp-read.service`

## Follow-up route

Revisit this decision when upstream Codex supports the exact modern server and
Tasks pair without the bounded derivative, when MCP publishes a later stable
wire version, or before granting Tasks to any candidate or effect contour.
