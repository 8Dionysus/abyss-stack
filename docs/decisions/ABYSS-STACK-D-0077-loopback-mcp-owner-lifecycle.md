# Loopback MCP Owner Lifecycle

- Decision ID: ABYSS-STACK-D-0077
- Status: accepted
- Date: 2026-07-13
- Owner surface: `mcp/services/` and `mechanics/runtime-lifecycle/parts/user-unit/`

## Index Metadata

- Original date: 2026-07-13
- Surface classes: MCP transport, loopback owner lifecycle, Configs projection
- Stack lanes: MCP access plane, runtime lifecycle, config projection
- Mechanic parents: runtime-lifecycle, config-projection
- Guard families: loopback-only exposure, source/deployed parity, per-owner canary, authority preservation
- Posture: accepted local transport consolidation rationale

## Context

Portable stdio lets every MCP package run without a daemon, but one server per
Codex process duplicates package state and memory. A direct local canary using
the same read-only owner measured four stdio processes at 256,880 KiB RSS and
one shared HTTP process at 65,728 KiB RSS, a 74.4 percent reduction. Protocol
canaries returned equal tool, resource, template, prompt, and structured
payload inventories through both transports.

The live rollout also exposed a stronger lifecycle defect: deployed services
had depended on an unlanded local server-wrapper change. Clean source declared
HTTP readiness and then exited because its entrypoint still hardcoded stdio.
Transport behavior, Configs projection, user-unit lifecycle, and runtime
freshness therefore need one source-owned contract rather than deploy-local
repair.

## Options considered

1. Keep one stdio process per client and accept duplicated resident memory.
2. Introduce one shared gateway that proxies every MCP owner.
3. Keep stdio portable while allowing one explicit loopback-only shared HTTP
   process per owner, with source-owned units and deployed-path parity.

## Decision

Choose option 3.

This decision supersedes only the earlier stdio-only or future-non-stdio
transport clauses in `ABYSS-STACK-D-0035`, `ABYSS-STACK-D-0036`,
`ABYSS-STACK-D-0037`, `ABYSS-STACK-D-0066`, `ABYSS-STACK-D-0071`,
`ABYSS-STACK-D-0072`, and `ABYSS-STACK-D-0075`. Their read-only, owner, proof,
mutation, and source-authority boundaries remain in force.

Every stack-owned MCP package keeps stdio as its default. When
`AOA_MCP_TRANSPORT=streamable-http` is explicit, the package may bind only
`127.0.0.1`, `localhost`, or `::1`; unsupported transports and non-loopback
hosts fail closed. Each owner has a stable default port from 5420 through 5429,
with an explicit environment override available for bounded canaries.

`aoa-mcp-http@.service` runs one deployed workspace wrapper per owner and
`aoa-mcp-http.service` groups the nine wrappers currently present in the shared
Codex plane. The bundle is not a proxy and does not merge owner authority.
`tos-corpus` implements the guarded transport contract on port 5429 but remains
outside the default bundle until its workspace wrapper and live canary exist.

Source-to-Configs sync owns `mcp/`, `schemas/`, and `systemd/` projection.
Preview, parity, unit linking, process restart, and protocol canary remain
separate gates. Installing source-managed units preserves existing masks and
never starts or restarts a service. Operators advance one owner at a time only
after source/deployed parity is green.

## Rationale

Per-owner loopback processes remove client-count memory multiplication without
creating a new gateway authority or network surface. Portable stdio remains
available for isolated use and package validation. Stable ports and deployed
workspace wrappers make runtime identity inspectable, while fail-closed host
checks prevent a local optimization from silently becoming remote exposure.
Separating install from restart preserves operator control and makes partial
rollback possible.

## Consequences

- Positive: multiple Codex clients can share one process per local owner.
- Positive: stdio and HTTP protocol inventories are contract-tested against the
  same package implementation.
- Positive: session-memory preflight can distinguish attached shared HTTP,
  missing owner, stale owner, invalid configuration, and stdio child posture.
- Tradeoff: the host now carries explicit per-owner ports and user-unit
  lifecycle that must be checked during deployment.
- Tradeoff: tool-schema changes can require both owner and client restart even
  when existing implementation bodies can auto-reload.
- Follow-up: add a workspace wrapper and live canary before admitting
  `tos-corpus` to the bundle.
- Follow-up: any remote, wildcard-bind, authenticated gateway, proxy, or
  cross-host route requires a later decision and threat-model review.

## Source surfaces

- `mcp/services/README.md`
- `mcp/services/*/src/*/server.py`
- `mcp/services/aoa-session-memory-mcp/src/aoa_session_memory_mcp/core.py`
- `systemd/user/aoa-mcp-http@.service`
- `systemd/user/aoa-mcp-http.service`
- `systemd/user/managed-units.txt`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `mechanics/config-projection/parts/sync/aoa_sync_configs.sh`
- `tests/test_runtime_lifecycle_user_unit.py`
- `tests/test_sync_parity_entrypoint_contracts.py`

## Follow-up route

Use source/deployed parity, `systemd-analyze --user verify`, per-package
validators, protocol inventory parity, and sequential live owner canaries
before treating the shared lifecycle as current runtime proof.
