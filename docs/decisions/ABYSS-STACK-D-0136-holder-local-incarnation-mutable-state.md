# Holder-Local Incarnation Mutable State

- Decision ID: ABYSS-STACK-D-0136
- Status: proposed
- Date: 2026-08-23
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`

## Index Metadata

- Original date: 2026-08-23
- Surface classes: runtime containment, public contract, source/runtime boundary
- Stack lanes: governed-execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: capability projection, incarnation identity, concurrency isolation
- Posture: proposed runtime rationale

## Context

The typed capability projection correctly denied ambient operator-control and
unknown entries, but the home lifecycle treated every non-local ambient name as
if it were a managed shared link. A Codex-created regular file or SQLite sidecar
under a denied ambient name was therefore either reported as projection-link
drift during repeated `prepare` or as an unexpected top-level home entry during
manifest loading. The realization-scoped home also gave sequential holders the
same mutable top-level namespace, so one duty could poison the next one. A
regular-file hard link could additionally expose an ambient inode through the
actor-local name, and a caller could reuse a namespace string without proving
the typed responsibility context that owned it. The first repair also left four
lifecycle edges at the generic owner boundary: the ambient inode walk was only
a current-path observation, config replacement could reach metadata mutation
before final alias admission, concurrent first preparation used existence
snapshots as rollback ownership, and the manifest and holder-receipt schemas
did not express their runtime compatibility and complete binding requirements
at the same version boundary.

## Options considered

- Add filename-specific exceptions for the observed database and sidecar names.
- Permit arbitrary actor-local top-level state in the projected home.
- Derive actor-local state from the current typed denied projection, reject
  inode aliases and replacement races, and bind every newly created holder to a
  digest of the typed holder/task/run responsibility context with a persistent
  non-replacing claim, while retaining marked legacy v2 homes for compatibility.

## Decision

Use the third route. The runtime records the derived denied-entry set as
`actor_local_state_names`; those entries may be absent or materialize as
regular files/directories owned by the actor, but never as symlinks, special
files, multiply linked files, or inodes also present in the ambient home.
Validation opens entries without following symlinks and rechecks their
device/inode/mode, so replacement during validation fails closed. Shared
entries continue to require an exact symlink to the ambient source. A prior
shared symlink may be removed only when the current typed projection demotes
that entry to denied; a regular local shadow is preserved.

Current typed homes emit v3 denied-state provenance: one bounded record for
each current denied name binds the ambient entry identity, when present, to the
admitted local-tree digest. A changed ambient identity is accepted only when
the local tree is unchanged, so unlink/replace cannot turn a previously
ambient-derived alias into accepted holder-local state. The record is bounded
by the current projection and is not a filename/history denylist. During one
materialization, the initial ambient inode snapshot is retained through the
final local-tree walk as a runtime-owned freshness boundary; its directory-entry
identities are retained from descriptor-relative enumeration, so a rename during
stat cannot erase the original inode from the snapshot. A replaced directory is
never traversed as ambient provenance. The snapshot is discarded after that
attempt and is not a filename/history denylist. Every file writer
pins and revalidates the target parent descriptor before creating, replacing,
or mode-updating a file, safely admits the existing target before its first
effect, and stages replacement bytes through a separate unnameable descriptor
before atomic publication. A parent rename, symlink replacement, or staged
write failure is rejected without changing ambient bytes or mode or destroying
the prior target. An interrupted named staging link is recovered only after
moving it into a private quarantine and revalidating its retained inode; an
aliased or replaced stage fails closed without deleting the foreign inode.

New homes require the exact bytes of a typed holder/task/run responsibility
context. The digest of that context selects a holder-local directory below the
realization coordinate and is carried into the manifest and holder receipt. A
persistent non-replacing claim reserves the home for one responsibility
lifecycle, so a mismatched, reassigned, overlapping, or sequential launch is
rejected. Once published, the claim freezes the home against every later
preparation: ambient changes and newly supplied grants cannot rewrite or widen
the live holder. Claim publication and preparation share a serialization
boundary formed by the pinned runtime directory plus its runtime-owned
single-link regular lock file. The named lock is revalidated after acquisition
and is never mode-normalized through an alias, so a lock-name replacement cannot
split critical sections or mutate an external inode. New files are published
from unnameable temporary descriptors, and existing targets are admitted
read-only, written to a fully fsynced unnameable staging descriptor, and
revalidated before atomic replacement. An
unpublished root is owned by an exact token before materialization, and only
a tokened unmarked root can be rolled back or recovered as stale. Canonical
launch reloads and digest-checks the manifest while that lock is held, so a
concurrent manifest replacement fails closed before claim publication rather
than binding stale launch evidence. A missing
typed binding remains valid only for an existing legacy v2 ownership marker and
cannot satisfy canonical launch. Every v2 manifest, including one carrying
typed binding data or denied-state provenance, is rejected by canonical launch
until preparation rewrites it to v3; a provenance-bearing v2 marker is not a
schema-valid compatibility shape and is rejected by the loader on any route.
Holder receipts require the complete runtime binding, including
`runtime_state_root` and `closeout_route`. A receipt carrying an immutable
manifest snapshot also requires `holder_binding` in the public schema, matching
the runtime snapshot loader for both v3 and legacy-v2 snapshots; pre-snapshot
compatibility receipts remain readable without that conditional field. Rebind
reserves the same holder claim under the preparation lock before publishing a
replacement receipt; if canonical launch already claimed the home, rebind
transfers the receipt binding from the superseded receipt under that lock. It
accepts an existing output only when it is the same complete canonical receipt
apart from creation time, and restores the exact prior claim bytes through a
validated descriptor if receipt publication fails. Owner-token cleanup likewise
revalidates its retained descriptor before unlinking, so a same-name
replacement cannot delete a newly published marker. An exact-claim retry
remains idempotent.

## Rationale

The denied set is an owner-authored semantic projection, not a hardcoded list of
filenames. This preserves default-deny even when Codex creates a local file with
the same basename as ambient operator-control state. The top-level type check
keeps unknown links and arbitrary special entries outside the actor-local
surface. A holder coordinate makes concurrency explicit and durable without
putting actor, task, Goal, version, or path identity into policy.

## Consequences

- Positive: repeated prepare accepts legitimate denied local state before a
  claim, while a published claim freezes the complete home against later
  configuration, projection, permission, provenance, and manifest changes.
- Positive: distinct holders retain separate mutable databases, sidecars, and
  lock directories while preserving realization-bound grants.
- Tradeoff: callers creating a new home must supply the owner-defined typed
  responsibility context and retain its claim until lifecycle closeout; old
  marked v2 homes remain a compatibility case until retired by their owner.
- Tradeoff: the runtime retains one persistent preparation lock per runtime
  root and one temporary owner token per unpublished first-preparation home;
  stale recovery is fail-closed if that tokened tree contains an ambient alias
  or an unsafe special entry, and retains a validated root descriptor through
  descriptor-relative deletion so a pathname replacement cannot redirect
  rollback into another home.
- Residual: source behavior and installed-artifact parity remain separate from
  host trust admission, live canary evidence, transport delivery, and owner
  acceptance.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-incarnation-home.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/DIRECTION.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

The external-Codex runtime owner must validate the installed content-addressed
release and a bounded live canary. The host artifact owner must admit the exact
release subject before activation. No step here grants app-server effect
authority, owner acceptance, master wake, or Goal completion.
