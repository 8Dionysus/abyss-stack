# Decision Cache Effect Isolation

- Decision ID: ABYSS-STACK-D-0089
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/services/aoa-decisions-mcp/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, decision graph, runtime policy
- Stack lanes: MCP services, decision lane, organ access fabric
- Mechanic parents: runtime-lifecycle
- Guard families: effect isolation, fail-closed freshness, owner cache
- Posture: accepted effect-isolated cache rationale

## Context

`ABYSS-STACK-D-0066` required lazy graph refresh before every MCP read. That
kept the navigation graph current, but it also made every nominal read capable
of creating a directory, acquiring a lock, and rewriting persistent cache
files. The owner-bounded access fabric established by
`ABYSS-STACK-D-0087` classifies that behavior as an internal effect. A read
credential must not be able to invoke it indirectly.

## Options considered

- Keep lazy refresh and classify the entire Decisions MCP as internal effect.
- Treat ignored cache writes as harmless and retain one shared read bearer.
- Split cache preparation from graph reads, require parity in the read
  contour, and fail closed when the prepared cache is missing or stale.

## Decision

Choose the third option.

The default Decisions MCP contour is `read`. It may compute the current local
input fingerprint and inspect existing graph and summary files, but it cannot
create the output directory, acquire the refresh lock, or rewrite cache
output. A missing or stale cache makes graph reads fail closed with an explicit
owner-refresh route.

The `internal_effect` contour is a separate process surface. It exposes cache
posture and explicit refresh only. It does not expose decision search, packet,
resource, or prompt surfaces. When deployed, it uses a credential distinct
from the read contour. The owner-local CLI remains a valid non-MCP preparation
route.

This decision narrows the automatic-refresh part of
`ABYSS-STACK-D-0066`. It preserves deterministic fingerprinting, local-only
freshness claims, source-posture warnings, cache output location, and
repo-local decision authority.

## Rationale

The split makes an important negative claim directly testable: invoking or
enumerating the read MCP surface cannot cause persistent cache writes. It also
keeps freshness fail-closed without incorrectly promoting an ignored cache to
source authority.

## Consequences

- Operators or an admitted internal-effect process must prepare the graph
  before the read contour serves packets.
- A changed local decision lane temporarily blocks reads instead of triggering
  a hidden write.
- Read and internal-effect processes require separate credentials, lifecycle
  declarations, and receipts before runtime admission.
- The existing lazy-refresh CLI and core remain available only where cache
  writes are explicitly allowed.

## Source surfaces

- `mcp/services/aoa-decisions-mcp/AGENTS.md`
- `mcp/services/aoa-decisions-mcp/README.md`
- `mcp/services/aoa-decisions-mcp/DESIGN.md`
- `mcp/services/aoa-decisions-mcp/docs/BOUNDARIES.md`
- `mcp/services/aoa-decisions-mcp/docs/THREAT_MODEL.md`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/core.py`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/server.py`
- `mcp/services/aoa-decisions-mcp/tests/test_decisions_mcp.py`
- `systemd/user/aoa-organ-mcp-read@.service`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`

## Follow-up route

Add separate owner-and-contour credentials and lifecycle units, then admit the
read contour only after package, deploy, schema, grounded canary, proof,
acceptance, and rollback evidence are complete.
