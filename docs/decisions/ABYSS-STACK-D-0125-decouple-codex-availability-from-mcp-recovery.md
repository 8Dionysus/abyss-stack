# Decouple Codex Availability From MCP Recovery

- Decision ID: ABYSS-STACK-D-0125
- Status: accepted
- Date: 2026-08-19
- Owner surface: `mcp/services/_shared/codex_http_client.sh`

## Index Metadata

- Original date: 2026-08-19
- Surface classes: MCP access plane, runtime lifecycle, operator client
- Stack lanes: MCP services, runtime lifecycle, Codex consumer
- Mechanic parents: runtime-lifecycle
- Guard families: fail open client, guarded repair, exact runtime identity, bounded recurrence
- Posture: accepted availability and self-repair boundary

## Context

The modern read fleet recovery was a synchronous pre-exec dependency of every
MCP-consuming Codex launch. After a host Python update changed the bytes behind
the venv interpreter symlink, the stack runtime verifier correctly rejected the
measured closure. Admission recovery could not repair that runtime and retried
the expensive two-phase canary transaction every thirty seconds. Codex then
waited on the failing transaction and exited, making an auxiliary access plane
a single point of failure for the operator client.

## Options considered

- Keep synchronous readiness and require manual runtime reprovision after host updates.
- Disable measured runtime integrity or bypass admission when recovery fails.
- Make the MCP runtime self-contained, let guarded lifecycle automation repair
  exact deployed drift, and keep Codex available while MCP recovers independently.

## Decision

Choose the third option. Runtime provisioning copies the bootstrap interpreter
into the published venv and measures that private closure. Admission refresh
verifies the stack runtime before bootstrap and invokes a separate manual-only
repair oneshot when verification fails. The repair action rebuilds only from
the deployed package and artifact-hashed lock, preserves all stopped-plane,
unit-identity, source-lock, runtime-lock, journal, and non-symlink guards, and
must succeed before admission continues.

The boot timer remains the primary recovery owner but backs off to five-minute
recurrence. The Codex launcher performs a cheap exact fleet check, requests the
same recovery oneshot with `--no-block` when needed, reports degradation once,
and executes Codex immediately. MCP readiness remains fail closed for MCP
authority; Codex availability is fail open because the operator client is not
itself an MCP admission contour.

## Rationale

Security and availability are separate boundaries. Starting Codex does not
authorize a missing or stale MCP server, while blocking Codex cannot repair
that server and removes the operator's primary recovery surface. A copied,
measured interpreter prevents ordinary host package replacement from mutating
an existing runtime. A separate guarded repair unit retains the exact source,
lock, stopped-plane, and sandbox contract without widening the admission
controller's ordinary write surface.

## Consequences

- Positive: host Python replacement no longer invalidates the published venv
  merely by changing a symlink target.
- Positive: a drifted but exactly reproducible runtime repairs before the
  bootstrap-to-production admission handoff.
- Positive: Codex starts even when MCP recovery fails or is still running.
- Tradeoff: a Codex session opened during genuine MCP downtime may retain
  unavailable MCP clients until a later session, but the operator is not locked
  out and recovery continues independently.
- Tradeoff: guarded runtime repair may use outbound package retrieval for the
  exact hash-locked closure when local artifacts are absent.
- Follow-up: remove the bounded custom Codex runtime only after the ordinary
  installed Codex exposes equivalent per-server modern-protocol selection and
  the admitted Tasks app-server methods.

## Source surfaces

- `mcp/services/_shared/codex_http_client.sh`
- `scripts/aoa-refresh-modern-mcp-admission`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `systemd/user/abyss-mcp-modern-admission-refresh.timer`
- `systemd/user/abyss-stack-mcp-runtime-repair.service`
- `tests/test_runtime_lifecycle_user_unit.py`

## Follow-up route

Rehearse interpreter replacement, guarded repair, admission recovery, and
non-blocking Codex launch from deployed source. Keep MCP authority fail closed;
do not reintroduce client unavailability as an admission control.
