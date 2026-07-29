# Receipt-Bound SDK Routing Cutover

- Decision ID: ABYSS-STACK-D-0086
- Status: accepted
- Date: 2026-07-25
- Amended: 2026-07-29
- Owner surface: `mechanics/federation-seams/parts/sync-wrapper/`

## Index Metadata

- Original date: 2026-07-25
- Surface classes: runtime route contract, owner succession, artifact consumer admission
- Stack lanes: runtime mirror, operator cutover, compatibility rollback, SDK-only operational rollback
- Mechanic parents: federation-seams
- Guard families: artifact trust, routing G5, runtime closure, rollback
- Posture: accepted inert canonical-intake capability

## Context

The SDK canary proved that exact SDK-produced routing bytes load in the real
runtime and can be rolled back. The public release candidate then established
immutable release trust. Neither result can authorize normal runtime closure:
the canary intentionally carries all-false G5 authority, while release trust
proves bytes rather than canonical ownership.

The final switch is a distributed transition across the SDK source owner,
stronger artifact owner, runtime owner, and predecessor. Requiring each owner
to report the other owners' completed future state would create a circular
proof dependency. Reusing the canary adapter would instead collapse evidence
preparation and authority execution into one ambiguous posture.

The first live switch preceded the self-contained embedded subject ledger.
That mirror remained byte-exact but could not satisfy the strengthened
checkout-free runtime inspection. Compatibility rollback also still consumed
the predecessor implementation, which is not an acceptable operational
dependency at consumer-zero.

## Options considered

- Widen `aoa-routing-canary` so a flag can make its existing manifest
  canonical.
- Let ordinary federation sync select either producer from ambient checkout
  state.
- Add a separate receipt-bound canonical intake and execute G5 as an
  authorized phase followed by an observed execution receipt.

## Decision

Keep the canary adapter permanently non-canonical. Add
`scripts/aoa-routing-cutover` as a separate, inert capability for the G5
transition.

The cutover accepts only an exact `runtime` trust verdict selecting the latest
public-release record, a verified subject store materialized for that intent,
and an owner-switch receipt that is itself one of the stored artifact
subjects. The receipt binds the SDK and predecessor source refs, stable
`aoa_routing_thin_router_v1` ABI, compatibility-window start, retained
rollback posture, and exact G5 authority flags.

Live materialization additionally requires:

- the exact `Knowledge/federation/aoa-routing` target shape;
- a named operator change record;
- a disjoint sibling rollback root;
- atomic activation.

Route-api recognizes `routing_producer_posture: sdk_canonical` only when the
receipt, producer admission including the exact required trust controls,
subject bytes, public-release trust record, and mirror hashes agree. Only the
separately recorded
`authorized_live_cutover` posture may satisfy normal runtime closure; an
isolated rehearsal remains non-closing.

The transition is two-phase:

1. the SDK receipt authorizes one exact switch after canary, rollback, and
   release evidence agree;
2. the runtime cutover executes it, after which owner evidence records the
   observed machine and runtime refs.

The authorization phase cannot claim that live execution already happened.
The execution phase cannot change the receipt's owner or ABI decision.

After the switch, refresh an already SDK-canonical live mirror only through
`refresh-materialized`. The route must verify the existing live bytes, durable
public-release trust record, receipt, refs, and authority against explicit
current inputs before it may replace the manifest. Before that replacement it
must seal and validate a disjoint self-contained SDK rollback tree from the
same admitted subject store.

The refreshed manifest binds that SDK tree as
`primary_operational_rollback`, records that predecessor implementation bytes
are not required, and keeps the predecessor binding as compatibility history.
`rollback-sdk` may then restore the SDK tree atomically without reading or
mutating the predecessor tree. It retains the displaced target, records a
durable SDK rollback receipt, and preserves SDK source ownership.

## Rationale

A distinct adapter makes the authority change visible and testable instead of
turning a canary boolean into production authority. Binding the receipt as a
verified artifact subject prevents a local side file from upgrading trusted
bytes. Requiring a public-release runtime verdict keeps normal consumption
separate from host-managed canary trust.

Two-phase execution resolves the distributed proof cycle without allowing two
canonical producers. Before the cutover, `aoa-routing` remains canonical.
After the receipt-bound cutover, `aoa-sdk` is canonical and the predecessor is
only compatibility and rollback.

## Consequences

- Positive: canary and canonical runtime closure remain distinguishable.
- Positive: the live mutation is owner-routed, exact-input, and atomically
  reversible.
- Positive: live activation persists and validates a canonical prepared stage;
  retry recognizes pre-rename, between-rename, and already-activated states.
- Positive: rollback refuses an unverified predecessor tree and persists a
  compatibility marker that survives route-api restart.
- Positive: an aborted rollback swap removes only the exact marker it staged,
  keeping the verified predecessor tree retryable without manual mutation.
- Positive: a retry recognizes exact pre-swap, between-swap, and
  already-restored filesystem states, validates the bound marker and trees,
  and either continues or returns an idempotent success.
- Positive: malformed trust-control collections degrade canonical readiness
  instead of crashing route-api health.
- Positive: file and directory `fsync` barriers precede transaction-state
  advancement and follow every tree rename, preserving recovery after reboot.
- Positive: route-api exposes only allowlisted receipt and trust summaries.
- Positive: the live mirror becomes self-contained for ordinary integrity
  inspection without reopening release admission or requiring a source
  checkout.
- Positive: operational recovery can restore an exact SDK-produced tree
  without the `aoa-routing` implementation; the predecessor tree remains
  untouched compatibility evidence.
- Positive: SDK-only rollback has the same fsync and retry law at pre-swap,
  between-swap, and already-restored boundaries.
- Tradeoff: G5 requires a new canonical registry record and subject store; the
  earlier candidate record cannot be silently promoted.
- Tradeoff: runtime rollback may temporarily serve predecessor bytes after
  G5. It does not reverse SDK source ownership, so health must report the
  compatibility rollback rather than claim predecessor canonical authority.
- Tradeoff: live cutover now requires the predecessor mirror to carry an exact
  manifest, stable ABI identity, and configured file hashes before it can
  become the rollback tree.
- Tradeoff: post-cutover refresh stores a second exact SDK runtime tree. This
  bounded storage cost removes the operational dependency on predecessor code
  and is explicit in the live manifest.

## Boundaries

- This decision adds an inert runtime capability; merging it does not switch
  the producer or mutate the live runtime.
- It does not change the routing ABI or source-owned next-hop meaning.
- It does not authorize `aoa-routing` archival.
- It does not add Agent OS Runner behavior to the owner switch.
- Runtime rollback does not create a second canonical source owner.
- SDK-only rollback changes runtime bytes, not source authority, release
  authority, compatibility-exit evidence, or the archival stop-line.

## Source surfaces

- `mechanics/federation-seams/parts/sync-wrapper/aoa_routing_cutover.py`
- `scripts/aoa-routing-cutover`
- `config-templates/Services/route-api/app/main.py`
- `mechanics/federation-seams/parts/sync-wrapper/README.md`
- `mechanics/federation-seams/parts/sync-wrapper/tests/test_routing_cutover.py`
- `mechanics/federation-seams/parts/federation-checks/tests/test_route_api_closure_status.py`

## Follow-up route

Use the exact canonical release and current `abyss-machine` admission to
refresh the live mirror, seal the SDK rollback tree, and prove SDK-only
recovery in a disposable live-shaped environment. Preserve the predecessor
tree as compatibility history until compatibility exit and consumer-zero;
archive authority remains a separate operator gate.
