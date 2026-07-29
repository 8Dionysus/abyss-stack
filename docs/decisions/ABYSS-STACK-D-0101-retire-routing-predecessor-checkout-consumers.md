# Retire Routing Predecessor Checkout Consumers

- Decision ID: ABYSS-STACK-D-0101
- Status: accepted
- Date: 2026-07-27
- Owner surface: `mechanics/federation-seams/parts/sync-wrapper/`

## Index Metadata

- Original date: 2026-07-27
- Surface classes: runtime route contract, owner succession, consumer retirement
- Stack lanes: runtime mirror, governed execution, compatibility trials
- Mechanic parents: federation-seams, governed-execution, inference-pilots
- Guard families: consumer zero, routing G5, artifact trust, rollback
- Posture: accepted SDK-canonical consumer cut

## Context

`ABYSS-STACK-D-0086` established the receipt-bound path that can materialize an
admitted `aoa-sdk` routing release into the stable runtime namespace
`Knowledge/federation/aoa-routing/`. After G5, however, four older stack paths
could still consume the predecessor checkout directly:

- ordinary federation sync could rebuild the runtime mirror from
  `AOA_ROUTING_ROOT`;
- governed execution could mutate an explicit `aoa-routing` target;
- the active local-trial compatibility corpus could validate or mutate the
  predecessor checkout;
- the eval-candidate MCP unit could discover and write predecessor-local
  `evals/` surfaces.

Those paths did not change route-api's canonical-owner verdict, but they kept a
second operational producer and mutable consumer surface alive. Runtime
adapter completion therefore did not yet prove consumer-zero.

The stable `aoa-routing` layer name, ABI epoch, route endpoints, cutover
command name, and predecessor rollback provenance are compatibility contracts.
They must not be confused with a continued source-checkout dependency.

## Options considered

- Keep predecessor checkout sync as an emergency repair path.
- Make federation sync select the SDK or predecessor from ambient checkout
  availability.
- Remove the stable `aoa-routing` runtime namespace together with the
  checkout.
- Keep the stable ABI and rollback metadata, but retire every active path that
  reads or mutates the predecessor checkout.

## Decision

Choose the final option.

Ordinary `aoa-sync-federation-surfaces` becomes check-only for the
`aoa-routing` layer. It verifies the integrity and embedded provenance of an
already admitted SDK-canonical materialization without requiring any SDK or
predecessor checkout. It cannot sync or auto-repair that layer. A missing or
drifted mirror routes explicitly to receipt-bound
`scripts/aoa-routing-cutover materialize`.

`scripts/aoa-routing-cutover` gains a read-only materialized inspection mode.
This mode verifies current bytes, manifest hashes, SDK identity, G5 authority,
owner-switch receipt, and embedded trust provenance. It does not re-prove the
external subject store or public-release admission; the existing exact-input
`check` operation remains authoritative for that stronger claim.

Governed execution retains only the `abyss-stack` mutation target. The
predecessor-specific detector, default roots, policy entries, canaries,
deterministic edit helpers, and promotion fixtures are retired. A request for
the old target fails closed.

The active local-trial compatibility runner keeps old case IDs only where they
are required to interpret existing logs. Current read-only routing cases point
to `aoa-sdk` owner sources or the stable route-api runtime projection. The two
predecessor mutation cases are removed from the active W4 catalog and remain
available only as historical provenance under the legacy trial route.

The eval-candidate MCP allowlist drops the predecessor `evals/` root and its
systemd write grants. The SDK owner root remains admitted independently.

## Rationale

A compatibility rollback tree is useful only if normal operation cannot
silently turn it back into a producer. Removing checkout discovery from sync,
governed mutation, and executable trials makes the G5 owner switch an
operational fact rather than a route-api label.

Keeping the stable namespace and wire names avoids an unrelated ABI migration.
Adding a bounded materialized inspection preserves ordinary health checks
without weakening the exact receipt-bound cutover gate.

## Consequences

- Positive: normal runtime health and profile setup no longer require an
  `aoa-routing` checkout.
- Positive: only an admitted SDK release can produce canonical routing mirror
  bytes.
- Positive: governed mutation cannot maintain or revive the predecessor.
- Positive: compatibility trials continue to interpret old logs while current
  owner assertions and executable validation follow `aoa-sdk`.
- Tradeoff: routing mirror drift cannot be auto-repaired by ordinary
  federation sync; operators must repeat the explicit cutover admission.
- Tradeoff: predecessor-specific governed canary and W4 mutation coverage is
  retired rather than redirected to a misleading SDK mutation contour.
- Tradeoff: stable runtime and rollback artifacts continue to contain the
  literal name `aoa-routing`; lexical absence is not the consumer-zero
  criterion.

## Boundaries

- This decision does not remove the stable `aoa-routing` ABI, runtime layer,
  route endpoints, canary command, or cutover command.
- It does not delete the retained predecessor rollback tree or its provenance.
- It does not prove compatibility-window exit or the required consecutive
  post-cutover validation cycles.
- It does not authorize repository archival. Archival remains forbidden
  without consumer-zero evidence, compatibility exit, and separate exact
  operator approval.

## Source surfaces

- `mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh`
- `mechanics/federation-seams/parts/sync-wrapper/aoa_routing_cutover.py`
- `config-templates/Configs/agent-api/governed-execution-policy.yaml`
- `config-templates/Configs/agent-api/governed-canary-catalog.json`
- `mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py`
- `mechanics/inference-pilots/parts/local-trials/compatibility-runners/aoa-local-ai-trials`
- `mechanics/inference-pilots/parts/quiet-bridge-commands/runners/aoa-w5-pilot`
- `mechanics/inference-pilots/parts/quiet-bridge-commands/runners/aoa-w6-pilot`
- `mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py`
- `systemd/user/aoa-evals-mcp-candidate.service`
- `scripts/validators/runtime_route_contracts.py`
- `docs/runtime/PATHS.md`
- `docs/install/DEPLOYMENT.md`
- `docs/profiles/PROFILE_RECIPES.md`

## Follow-up route

Prove the active source consumer scan is zero, run the stack validation and
release gates, and land this change only in the coordinated SDK-first wave.
After landing, complete the required consecutive SDK validation and real
execution cycles before evaluating compatibility exit. Keep archival
unauthorized unless the operator later grants exact separate approval.
