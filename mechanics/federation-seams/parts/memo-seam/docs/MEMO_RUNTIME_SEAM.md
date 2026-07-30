# MEMO RUNTIME SEAM

This document defines the `abyss-stack` landing for `aoa-memo` in the runtime body.

It does not turn `abyss-stack` into the memory authority layer.
It defines how the runtime may mirror public-safe memo surfaces, inspect them through the existing `route-api`, and export bounded memo candidate artifacts without promoting them automatically.

## What is mirrored

The memo runtime landing mirrors a bounded public-safe subset of `aoa-memo` into:

`${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/`

That mirror currently includes:

- memo doctrine docs needed for runtime orientation and recurrence support
- compact doctrine and object catalogs
- compact doctrine and object capsule packs
- full section packs for doctrine and object inspection
- router-ready and object-facing recall contracts
- the checkpoint-to-memory contract example
- the core memory and checkpoint-to-memory schemas

The mirror is runtime-local and exact for its allowlisted subtree.
It is not a loose copy of the whole `aoa-memo` repository.

## What `route-api` exposes

The existing localhost-only `route-api` remains the single federation facade on `127.0.0.1:5402`.

The landing adds a `/memo/*` namespace for bounded read-only inspection:

- `GET /memo/registry`
- `GET /memo/catalog`
- `GET /memo/object-catalog`
- `GET /memo/checkpoint-contract`
- `POST /memo/inspect`
- `POST /memo/capsule`
- `POST /memo/expand`
- `POST /memo/recall-contract`
- `POST /memo/writeback-map`

These surfaces are advisory and read-only.
They do not access live scratchpad, do not perform free-text recall, do not write into `aoa-memo`, and do not replace memo-owned authority.

## What the runtime exports

The runtime export seam is filesystem-first.

`scripts/aoa-export-memo-candidate` reads the mirrored checkpoint-to-memory contract and emits bounded runtime-owned candidate artifacts under:

- `${AOA_STACK_ROOT}/Logs/memo-exports/latest/`
- `${AOA_STACK_ROOT}/Logs/memo-exports/records/`

These artifacts are reviewable candidates, not memo objects.
They are the runtime-side handoff pack for possible future import or review in `aoa-memo`.

The export seam maps only the currently mirrored contract surfaces:

- `checkpoint_export`
- `approval_record`
- `transition_record`
- `execution_trace`
- `review_trace`
- `distillation_claim_candidate`
- `distillation_pattern_candidate`
- `distillation_bridge_candidate`

## Active-organ delivery receipt

C20 `RuntimeDeliveryReceipt` is the runtime-side, content-minimized evidence
contract for one bounded active-organ delivery attempt. Its canonical stack
schema is
`../schemas/active-organ-runtime-delivery-receipt.schema.json`.

The receipt distinguishes `attempted`, `delivered`, `suppressed`, `expired`,
and `failed`. It pins the exact recall intent, admitted run plan, intervention
decision, trigger, anchor freshness, consumer, tenant, data/risk classes,
policy version, model/prompt/provider/hardware evidence ref, target adapter,
and runtime evidence refs. A delivered receipt requires a current anchor,
an admitted packet, and a `bounded_observation` decision. Silence, stale
anchors, expired admission, and failed transports remain explicit non-delivery
states.

The durable receipt is `refs_only`: packet content, prompt content, memory
content, payload digests, and error detail are forbidden. It grants neither
effect authority nor memory semantic authority, cannot widen policy, and
requires a new admission check before a new attempt. The schema and examples
describe source contract posture only; their presence does not prove a live
delivery service or deployed runtime consumption.

### Codex owner-orientation adapter

`aoa_memo_owner_orientation` is a read-contour, in-process delivery adapter
for the first bounded consumer. It requires two exact inputs:

- an SDK-owned `codex_owner_orientation_plan_v0`
- an aoa-memo-owned `codex_owner_orientation_memo_bundle_v0` containing
  valid C08 and C09

The compatibility pin fixes the plan schema, memo contract schema, consumer
profile, C11 policy, memo-bundle schema, and C20 schema. The adapter verifies
plan, item, bundle, C08, and C09 content digests; D0/R1 explicit pull; current
C18/C19; reviewed-current source posture; budget/mode agreement; and the
absence of raw `.aoa`, writes, promotions, effects, and action authority.

The adapter does not query or rank memo surfaces. On success it returns the
plan's exact items and a C20 receipt. Silence and the two no-memory modes are
suppressed with an empty payload. Expired bounded plans emit an expired C20
with an empty payload. Receipts remain refs-only and are returned, not
persisted by the adapter.

### Source-local selective canary

`deliver_canary_orientation` is a non-exported source-local method for the
Phase 8 mechanism lab. It does not widen `aoa_memo_owner_orientation` and is
not registered as an MCP tool, service route, Codex hook, timer, or deployed
consumer.

The method accepts exact pinned release, shadow, memo-bundle, and machine
admission artifacts. It may return only the already-authored single
`source_linked_memory_observation`; it never ranks, selects, expands,
persists, or interprets memory. The C20 canary receipt stores only refs and
digests. It carries the randomized arm, policy window, prior delivered count,
source/currentness visibility, rollback target, and explicit non-authority
flags.

The runtime checks prior same-window receipts independently of the SDK count.
A second delivery is rate-limited even if a stale release still says zero.
Kill switch, holdout, semantic silence, expiry, host denial, count drift, or
any failed schema/pin/authority check returns no observation or rejects the
artifact. Rollback returns to `codex_owner_orientation_v0`; no write reversal
is needed because the canary has no write authority.

## Distributed erasure owner extension

The stack-owned
`../schemas/active-organ-runtime-erasure-owner-extension-v0.schema.json`
binds two distinct surfaces into the `aoa-memo` C14-C17 closure:

- ER4: runtime store, cache, and nervous-index descendants;
- ER5: export and backup/restore descendants.

The extension carries only worker and parent-owner bindings, digest-only
target refs, operation evidence, recovery-probe refs, result, residue, and
explicit retention exceptions. Restore recovery must be checked for both
surfaces. Project-root and host-root mutation remain forbidden because those
are not stack-owned erasure targets.

The schema and focused test are public-safe reference-lab evidence only. They
do not execute deletion, purge a backup, mutate a running service, disclose
private paths, or claim that the whole distributed erasure is complete. Any
residue, missing restore probe, or owner-extension drift must block a
plain-complete private-memory deployment at the memo manifest.

## What this landing does not do

This landing does not:

- auto-write memo objects from runtime traffic
- add a new host-facing port
- add a new writeback HTTP API
- make `langchain-api` write memory artifacts implicitly
- turn `abyss-stack` into the live memory store
- override `aoa-memo` object canon, review posture, or recall meaning
- persist private active-organ packet, prompt, or memory content in a delivery
  receipt
- treat a delivery receipt as proof of benefit, outcome quality, or policy
  approval
- turn the source-local adapter into a deployed service or hidden automatic
  Codex hook
- infer ER4/ER5 deletion from an absent cache, empty runtime, or unavailable
  restore path without a working positive control and negative recovery probe

## Operational route

Executable mirror refresh, route-api inspection, and candidate export commands
live in `../AGENTS.md`. This document owns the seam contract; the route card
owns agent-facing operation.

## One-line rule

`abyss-stack` may mirror `aoa-memo`, inspect its bounded recall surfaces, and emit runtime memo candidates, but it must not silently become `aoa-memo`.
