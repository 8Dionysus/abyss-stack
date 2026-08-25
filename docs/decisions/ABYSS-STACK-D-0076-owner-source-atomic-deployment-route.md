# Owner-source Atomic Deployment Route

- Decision ID: ABYSS-STACK-D-0076
- Status: accepted
- Date: 2026-08-24
- Owner surface: `mechanics/runtime-lifecycle/parts/deployment-route/`

## Index Metadata

- Original date: 2026-08-24
- Surface classes: runtime topology, source/runtime boundary, deployment route
- Stack lanes: runtime lifecycle, source checkout, operator deployment
- Mechanic parents: runtime-lifecycle
- Guard families: clean source identity, ignored-cache boundary, content manifest, release-root inode binding, effect-bound destination ownership, explicit claim ceiling, post-switch rollback, historical rollback event, atomic switch, durable activation recovery, predecessor rollback, deployment lock
- Posture: accepted owner-source deployment rationale

## Context

The source-only owner deployment direction needs a later deployment route for
an exact reviewed owner checkout without mutating the shared source checkout or
the installed runtime during source work. Existing Configs sync is a
non-destructive mirror boundary, while the existing managed checkout route can
reset and clean a destination in place. Neither provides the required
transactional identity and rollback boundary for this duty. The route must also
remain recoverable when the process stops after durable intent, after the
symlink switch, or while writing a receipt. Review of the first implementation
also showed that a second destination snapshot after `_finalization_admission`
was data, not proof that the route owned a later same-UID `os.replace`; rollback
target/seal comparison alone had the same defect.

The source owner, the host artifact-trust owner, and the runtime/deployment
owner are different responsibilities. A source commit/tree check, artifact
admission, and live runtime health therefore cannot be collapsed into one
green result. The first rollback implementation review further found three
independent gaps: displacement was random and unjournaled, device/inode/link
tuples could be reused by a later writer, and rollback finalization did not
publish a typed historical event that remained valid when a later writer
replaced the destination after the last current-state observation.

## Options considered

1. Update a managed destination checkout in place with fetch/reset/clean.
2. Require a signed/admitted package or artifact bundle as the only route.
3. Use a hybrid runtime-owned route: external typed admission, clean exact
   source validation, self-contained versioned Git release, atomic destination
   symlink switch, and explicit predecessor rollback.
4. Treat a post-switch snapshot or final recheck as the ownership proof and
   infer rollback authority from destination target/seal.

## Decision

Choose option 3, with an effect-bound ownership refinement that rejects option 4.

`abyss-stack` owns the route implementation under
`mechanics/runtime-lifecycle/parts/deployment-route/`. It stages a full
non-alternating Git clone for an exact clean commit/tree under a versioned
release identity. It refuses dirty source or destination state, stale or
mismatched admission, incomplete staging, cross-device paths, concurrent
deployment, and predecessor or activated-release ref/tree/clean drift. Each
staged release also gets a read-only sidecar seal bound to its exact path, root
device/inode, Git identity, and a content manifest of all present files,
directories, ignored entries, modes, metadata, and symlink targets. Special
files are rejected and symlinks are recorded without traversal. The route
revalidates that seal immediately before switching and again after the
destination switch. The lock coordinates cooperating route writers, but
staged rename alone cannot exclude a same-UID path replacement. The route
captures the temporary symlink's device/inode, mode, target, link text, and a
prepared-release owner token before the successful `os.replace`, then durably
records that owner with a committed switch event before an activation receipt
is written. Ordinary activation and `recover --action finalize` share this
contract. Their finalization is historical (`current_destination_claim: false`),
so a later writer is not misclaimed as the route's current destination; a
defensive post-switch read remains an integrity fence, not the atomicity proof.
A privileged actor that changes modes or bypasses the filesystem controls
remains outside this source-only guarantee. Ignored cache content is outside
Git's source identity and is not introduced by staging, but any ignored content
present in a release is covered by the release manifest; tracked and
non-ignored untracked content remains a hard failure. Activation writes a
durable recovery journal before the same-filesystem relative symlink plus
`os.replace` switch. A journaled interruption can be deterministically
finalized or rolled back, and rollback restores the recorded predecessor
without deleting releases. If the switch owner was not durably recorded,
recovery refuses to infer it from target or seal.

Rollback uses a portable protocol boundary rather than a kernel handle: the
intent journal allocates a deterministic displacement path, fresh sequence,
and prepared-operation token before any rename. `RENAME_NOREPLACE` moves the
owner there and the path is retained through the durable rollback-switch
marker. Every route-created displacement/predecessor path records exact
symlink/device/inode/mode/link identity; a pre-existing, replaced, or
wrong-kind path is rejected. The predecessor effect uses a canonical link
spelling derived from the activated release, release root, predecessor target,
and destination, bound to the prepared token, so a token/spelling replay or
inode-reusing later writer cannot satisfy the CAS. The destination parent is
fsynced after every destructive rename before its journal state advances, and
cleanup unlinks only an exact recorded object, fsyncing after each deletion.
The state machine explicitly covers B1 after displacement, B2 after predecessor
install/cleanup, B3 after the rollback-switch marker, B4 during receipt
publication, and B5 after inode reuse. Current-state fences run before the
rollback receipt and again before historical event publication. Rollback then
emits a typed `rollback_finalization` event using
`historical-rollback-event-v1`, with `current_destination_claim: false`; a later
writer after that last observation remains current without invalidating the
historical receipt or journal, and fresh reload validates the event and
converges. No post-publication finite fence is used as ownership proof.

The route admission is an input contract, not an `abyss-machine` artifact
signature. Artifact classes, signatures, SBOM/provenance, registry selection,
and trust gates remain host-owner concerns. This route does not create an
`aoa-stats` artifact class. Configs projection, dependency installation,
service operations, runtime health, semantic acceptance, and human acceptance
remain separate explicit routes.

## Rationale

The in-place checkout route has a destructive cleanup window and no atomic
destination identity; an interrupted reset can leave a partially updated
consumer. The artifact-only option has the strongest provenance potential but
cannot be honestly invoked for an owner package without a policy class and
admitted bundle supplied by the artifact owner. The hybrid keeps source review
and host trust separate while making the later switch and rollback
transactional, inspectable, and repeatable.

The self-contained clone avoids coupling an installed release to the mutable
object store of the source checkout. The lock and predecessor check make a
prepared receipt single-use against the observed destination state, but are
not a complete exclusion mechanism for a same-UID non-cooperating writer.
Alternatives such as a cooperative lock, a staged `os.replace`, or an inode
check only before the switch each leave a final-check-to-effect gap. A
pre-switch manifest/root-inode check catches staged tampering; the
post-switch manifest/root-inode/destination verification remains a defensive
integrity fence, while the pre-effect owner capture and durable event bind the
effect itself. A finite recheck, cooperative lock, or descriptor/rename
exchange without a cross-file receipt transaction cannot establish that
ownership. The durable intent/switch/receipt sequence makes an active
destination explicit instead of allowing a plain rejection with an unjournaled
new target. Rollback has its own `rollback_intent`,
`rollback_switch_complete`, and typed historical-finalization states, a durable
displacement record, and a canonical rollback owner. It carries those records
through retries; changed inode/link identity, even with the same target and
seal, is preserved in the historical event rather than misclaimed as current.
The rollback receipt is written only after the predecessor effect and cleanup
state are journaled and the pre-publication current-state fences pass; the
following event publication records that the route's destination claim has
ended, so a later writer does not invalidate the receipt or require a second
finite fence. Typed receipts bind
every finalized activation/rollback reference to the journal state digest and
immutable operation/source/destination/release/predecessor/admission identity.
Directory-open/fsync and receipt-write failures therefore return a
recovery-required result instead of claiming a completed durable receipt.
Nested source snapshots and recovery states make the authority ceiling
explicit so source preparation cannot be mistaken for runtime proof.

## Consequences

- The first source-only route can be tested entirely in disposable temporary
  Git repositories and destinations.
- A later installed activation still requires an operator-held admission and
  the separate artifact-trust decision where applicable.
- Release directories are retained for rollback and require bounded storage
  management by the owning deployment operator.
- The route adds a root wrapper, mechanic-local tests, nested receipt schemas,
  a recovery-journal schema, and validation topology entries.
- Release seals add a closed content manifest and root-inode binding; activation
  performs a post-switch integrity fence and durable predecessor rollback
  before any activation receipt is emitted.
- Activation receipts describe the historical atomic switch event and
  explicitly do not claim that the mutable destination is still current;
  rollback requires the durable destination owner token, displacement sequence,
  and rollback owner.
- Rollback keeps exact route-created displacement/predecessor identities through
  each pre-receipt state; B1-B5, path replay, cleanup replacement, fsync
  failure, and final-journal interleavings fail closed without object loss,
  overwrite, or a false rollback receipt.
- Configs sync remains the source/runtime mirror route for ordinary stack
  changes; this route is not a replacement for it.

Schema compatibility is intentionally explicit: the existing admission,
prepare, activate, and rollback schema identifiers remain v1 route contracts,
but their emitted nested objects are now closed and identity-bound. Activation
receipts emitted by this route require the recovery-journal binding; an older
receipt without that binding is not accepted as a new rollback-capable receipt.
The recovery journal is a separate v1 contract because it records durable
intermediate states rather than pretending that an activation receipt exists
before its write completes.

## Source surfaces

- `mechanics/runtime-lifecycle/AGENTS.md`
- `mechanics/runtime-lifecycle/PARTS.md`
- `mechanics/runtime-lifecycle/parts/deployment-route/README.md`
- `mechanics/runtime-lifecycle/parts/deployment-route/aoa_deploy_owner_package.py`
- `mechanics/runtime-lifecycle/parts/deployment-route/schemas/`
- `mechanics/runtime-lifecycle/parts/deployment-route/schemas/recovery-receipt.v1.json`
- `mechanics/runtime-lifecycle/parts/deployment-route/tests/test_deployment_route.py`
- `docs/install/DEPLOYMENT.md`
- `scripts/aoa-sync-configs`
- `scripts/validators/script_surface.py`
- `docs/validation/validation_lanes.json`

## Follow-up route

The operator/deployment holder should review the prepare receipts and run the
`abyss-machine` artifact-trust route before any installed activation. The
runtime lifecycle owner then performs explicit activation and live verification
as a separate duty; this decision must be revisited if a real admitted
`aoa-stats` artifact class or a different deployment substrate becomes
canonical.
