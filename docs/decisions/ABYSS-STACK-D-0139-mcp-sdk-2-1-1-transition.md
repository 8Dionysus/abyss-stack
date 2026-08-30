# MCP SDK 2.1.1 Transition And Central Runtime Identity

- Decision ID: ABYSS-STACK-D-0139
- Status: accepted
- Date: 2026-08-29
- Owner surface: `mcp/services/_shared/`
- Supersedes: `ABYSS-STACK-D-0108`

## Index Metadata

- Original date: 2026-08-29
- Surface classes: MCP access plane, dependency boundary, source/runtime boundary
- Stack lanes: MCP services, runtime lifecycle, protocol compatibility
- Mechanic parents: runtime-lifecycle
- Guard families: exact dependency identity, generated projection, fail closed, source/runtime parity
- Posture: accepted source transition with deployment pending

## Context

`ABYSS-STACK-D-0108` established the modern-only MCP route around an exact
Python MCP 2.0.0 runtime. The implementation has now moved all stack-owned
standalone packages to the native SDK v2 `MCPServer` surface and removed the
former `AbyssMCPServer`/private-server compatibility seams. The next supported
Python SDK release for this route is 2.1.1 and its required `mcp-types` package
must move as a pair.

The previous arrangement also left version, paths, ports, and deployment
identity vulnerable to repeated literals across packages and protocol probes.
That makes an SDK update needlessly dependent on synchronized hand edits and
can let a generated or deployed consumer lag behind the source decision.

## Options considered

- Keep the exact 2.0.0 runtime and defer the supported SDK update.
- Change each package and probe independently, retaining repeated version and
  deployment literals.
- Adopt 2.1.1 as the managed tested lock, keep the public package requirement
  on major 2 only, pair `mcp` with `mcp-types`, and derive package/probe/unit
  projections from one declarative runtime catalog.

## Decision

Choose the third option.

The shared MCP runtime catalog is the source for the admitted SDK major,
tested lock, exact upstream source revision, protocol revision, transport,
paths, limits, contours, credentials, and service units. Its current tested
lock is `mcp==2.1.1` paired with `mcp-types==2.1.1`, sourced from Python SDK
commit `0921d94a74db900dccd2d534842aa7b6160542d2`. Every stack-owned
standalone package admits only SDK major 2 through `mcp>=2,<3`; the managed
hash-locked environment pins the catalog's current tested pair exactly.

The native `MCPServer` runtime and generated package-local catalog projections
are the only implementation route. Protocol-lab runners and validators read
the same catalog, so a future supported SDK update changes one authority and
then regenerates and verifies its projections rather than requiring scattered
version literals.

This decision changes the source and test baseline. It does not claim that the
already-running deployed venvs have been replaced: the deployed runtime and
its 2.0.0 live receipts remain a separate source/runtime-parity blocker until
the official deployment path installs the exact 2.1.1 pair and fresh live
process-bound evidence passes. Candidate and internal-effect contours remain
manual-only and do not inherit read-contour admission.

## Rationale

Pairing `mcp` and `mcp-types` prevents the SDK's distribution and wire-model
surfaces from drifting independently. Keeping a major-only package contract
allows the shared catalog and managed lock to control the currently tested
minor release without scattering exact pins through fifteen packages.

The source revision, lock hashes, generated vendors, and fail-closed runtime
checks make the next update reviewable and reversible. They also preserve the
boundary between source readiness, deployment, process identity, transport
proof, semantic acceptance, and operator publication; a green source test
cannot be mistaken for an activated fleet.

## Consequences

- Positive: all stack-owned MCP packages use one native v2 runtime shape and
  one centrally declared 2.1.1 tested pair.
- Positive: generated package vendors and protocol receipts inherit version,
  source revision, transport, and path identity from the catalog.
- Positive: stale 2.0.0 live or pair evidence is reported explicitly instead
  of being accepted as current after a source-only update.
- Tradeoff: a deployment refresh is still required before the live fleet can
  claim 2.1.1; source readiness and installed-runtime readiness remain
  intentionally separate.
- Tradeoff: regenerating the complete hash lock still depends on a valid,
  retrievable pinned `aoa-sdk` artifact; this transition does not weaken that
  supply-chain check.

## Source surfaces

- `mcp/services/_shared/runtime-config.v1.json`
- `mcp/services/_shared/runtime-config.schema.json`
- `mcp/services/_shared/runtime_config.py`
- `mcp/services/_shared/build_runtime_config_vendors.py`
- `mcp/services/_shared/modern_runtime.py`
- `mcp/services/abyss-stack-mcp/requirements.constraints`
- `mcp/services/abyss-stack-mcp/requirements.lock`
- `requirements-dev.txt`
- `mcp/protocol-lab/scripts/runtime_catalog.py`
- `mcp/protocol-lab/scripts/validate_protocol_lab.py`
- `mcp/protocol-lab/scripts/run_kag_next_pair.py`
- `mcp/protocol-lab/scripts/run_kag_handle_pair.py`
- `mcp/protocol-lab/scripts/run_kag_cache_pair.py`
- `mcp/protocol-lab/CONTRACT.md`
- `ABYSS-STACK-D-0108` historical modern-only MCP rationale

## Follow-up route

Use the owner deployment route to install the exact 2.1.1 pair into the
managed runtime, refresh all eleven admitted read contours and their negative
wire proofs, then rerun the isolated pair and full fleet evidence. Do not
refresh or promote candidate/effect authority as a side effect. Revisit this
decision when the central tested lock or SDK major changes; such a change must
repeat source, generated, dependency, protocol, deployment, and rollback
checks.
