# Canonical KAG Cold-CAS Binding

- Decision ID: ABYSS-STACK-D-0136
- Status: accepted
- Date: 2026-08-24
- Owner surface: `mcp/services/aoa-kag-mcp/`

## Index Metadata

- Original date: 2026-08-24
- Surface classes: MCP access plane, source/runtime boundary, public contract
- Stack lanes: MCP read, KAG seam, deployment configuration
- Mechanic parents: `mechanics/federation-seams/parts/kag-seam`
- Guard families: source-owned authority, fail-closed delivery, public-safe projection
- Posture: accepted rationale

## Context

The canonical `aoa-kag` owner family is a v4 tiered distribution. Its query
loader accepts a verified cold-CAS root, but the stack MCP adapter had no
authored configuration path to provide that root. The adapter therefore could
not reproduce a complete owner read when cold objects were not present in the
Git-hot checkout.

## Options considered

- Patch the deployed `Configs` mirror: rejected because the runtime mirror is a
  projection and not source authority.
- Add a second CAS or service-local index: rejected because it would split the
  owner identity and bypass the existing v4 delivery route.
- Add an optional `AOA_KAG_ARTIFACT_ROOT` source/configuration seam and pass it
  to the owner loader: chosen.

## Decision

`AoAKagMCPState` accepts the authored `AOA_KAG_ARTIFACT_ROOT` binding as an
absolute path. The canonical adapter passes the value to `aoa-kag.load_family`
and sets `allow_shadow_git` to false whenever the value is configured. The
adapter accepts the current owner loader tuple while retaining only its source
index and validated family for query construction.

The binding selects a delivery route; it is not artifact admission, runtime
activation, semantic proof, or owner acceptance. Those claims stay with their
respective owners and receipts.

## Rationale

The stack owns MCP mapping, service configuration, and runtime integration;
`aoa-kag` owns family shape and retrieval semantics; `abyss-machine` owns
artifact trust. A narrow environment/configuration seam keeps those boundaries
observable and allows the owner loader to fail closed on missing or mismatched
cold objects.

## Consequences

- Positive: canonical MCP reads can bind the exact owner v4 CAS without a
  deployed hotfix or a shadow copy.
- Tradeoff: a configured root makes shadow fallback unavailable and requires a
  complete owner delivery.
- Follow-up: the established source projection and runtime admission routes
  must carry the authored configuration before live delivery is claimed.

## Source surfaces

- `mcp/services/aoa-kag-mcp/src/aoa_kag_mcp/core.py`
- `mcp/services/aoa-kag-mcp/src/aoa_kag_mcp/canonical.py`
- `scripts/aoa-lib.sh`
- `docs/runtime/PATHS.md`

## Follow-up route

Use the stack source projection/deployment route, then verify canonical MCP
transport and semantic exact-search results against current source and
projection identities.
