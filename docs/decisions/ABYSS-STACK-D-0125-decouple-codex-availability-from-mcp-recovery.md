# Decouple Codex Availability From MCP Recovery

- Decision ID: ABYSS-STACK-D-0125
- Status: accepted
- Date: 2026-08-19
- Amended: 2026-08-20
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
- Make the MCP runtime independently measured, let explicitly enabled guarded
  lifecycle automation repair exact deployed drift, and keep Codex available
  while MCP recovers independently.

## Decision

Choose the third option. Runtime provisioning copies the bootstrap interpreter
into the published venv and measures that private closure. Because Python's
stdlib may still be host-backed, read-only verification also executes isolated
stdlib and pinned dependency imports. Admission refresh verifies the stack
runtime before bootstrap and may invoke a separate opt-in repair oneshot when
verification fails, but only after the operator persists the reversible host
auto-repair policy. The repair action rebuilds only from the deployed package
and artifact-hashed lock. It holds the source lock throughout and excludes
candidate and internal-effect starts with an operation lock, while allowing the
working read fleet to retain its shared runtime locks during dependency
installation and replacement verification. Only a fully built replacement may
enumerate and briefly quiesce the active stack and organ readers, acquire the
exclusive runtime lock, and perform the atomic swap. Recurring maintenance and
candidate consumers hold operation/runtime locks; long-lived organ readers hold
the runtime lock through their process lifetime. Failure before quiescence
leaves every reader active; failure after quiescence restores the previous venv
and restarts every reader that had been active. Before quiescence, repair writes
a private grant bound to that runtime's exact measured content and recorded
identity. Only
the read contour may use the grant to survive source-identity drift after
rollback; candidate, internal-effect, and general verification stay strict, and
a successful replacement removes the grant. Exact repair-fallback counterparts for
the previously active endpoint set remain available until admission validates
and commits the production handoff. Any later admission failure restores that
bounded fallback before returning. The admission unit reserves twenty
minutes so the bounded ten-minute repair still leaves a separate admission
budget.

The boot timer remains the primary recovery owner but backs off to five-minute
recurrence. The Codex launcher performs a cheap exact fleet check, requests the
same recovery oneshot with `--no-block` when needed, reports degradation once,
and executes Codex immediately. It prefers the official standalone Codex and
explicitly enables that client's MCP 2026-07-28 feature; the bounded OS Abyss
fork is no longer the interactive default. MCP readiness remains fail closed for MCP
authority; Codex availability is fail open because the operator client is not
itself an MCP admission contour.

## Rationale

Security and availability are separate boundaries. Starting Codex does not
authorize a missing or stale MCP server, while blocking Codex cannot repair
that server and removes the operator's primary recovery surface. A copied,
measured interpreter prevents ordinary host package replacement from mutating
an existing runtime. A separate guarded repair unit retains the exact source,
unit-identity, lock, journal, non-symlink, and sandbox contracts without
widening the admission controller's ordinary write surface. Building the
replacement before the final quiescence keeps a package-index or dependency
failure from turning recoverable runtime drift into read-plane downtime. The
operation lock keeps non-read stack planes out of the interval while running
readers continue under their existing shared runtime locks. The unit-install
route creates the private operation lock before sandboxed upgraded units become
loadable, and every direct shared-venv consumer either holds both lifecycle
locks or participates in the final reader quiescence.

## Consequences

- Positive: host Python replacement no longer invalidates the published venv
  merely by changing a symlink target, while a broken host-backed stdlib is
  still caught by executable import verification.
- Positive: a drifted but exactly reproducible runtime repairs before the
  bootstrap-to-production admission handoff.
- Positive: dependency retrieval, build, or pre-swap verification failure does
  not stop the working read fleet.
- Positive: a post-quiescence activation failure atomically restores the prior
  runtime and every previously active reader; the stack peer uses an exact,
  read-contour-only rollback grant.
- Positive: failure after successful activation but before admission commit
  preserves the prior endpoint set through exact repair-fallback counterparts.
- Positive: Codex starts even when MCP recovery fails or is still running.
- Tradeoff: a Codex session opened during genuine MCP downtime may retain
  unavailable MCP clients until a later session, but the operator is not locked
  out and recovery continues independently.
- Tradeoff: guarded runtime repair may use outbound package retrieval for the
  exact hash-locked closure when local artifacts are absent; automatic use is
  denied until the host opt-in marker is explicitly installed.
- Follow-up: remove the bounded custom Codex runtime from the Tasks witness only
  after the ordinary installed Codex exposes the admitted Tasks app-server
  methods. It is no longer used by the interactive launcher.

## Source surfaces

- `mcp/services/_shared/codex_http_client.sh`
- `scripts/aoa-refresh-modern-mcp-admission`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `systemd/user/abyss-mcp-modern-admission-refresh.timer`
- `systemd/user/abyss-stack-mcp-runtime-repair.service`
- `systemd/user/abyss-stack-mcp-candidate.service`
- `systemd/user/abyss-stack-mcp-internal-effect.service`
- `tests/test_runtime_lifecycle_user_unit.py`

## Follow-up route

Rehearse interpreter replacement, guarded repair, admission recovery, and
non-blocking Codex launch from deployed source. Keep MCP authority fail closed;
do not reintroduce client unavailability as an admission control.
