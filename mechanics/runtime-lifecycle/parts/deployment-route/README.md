# Owner-source deployment route

## Mechanic card

### Trigger

Use this part when an owner-reviewed, source-only Git checkout must be staged
for a later operator-controlled deployment. The route is intentionally
separate from Configs projection and runtime lifecycle start/stop.

### abyss-stack owns

`runtime-lifecycle` owns the transactional destination mechanics: clean-source
identity checks, self-contained release staging, same-filesystem atomic symlink
replacement, deployment locking, durable activation recovery, and predecessor
rollback receipts.

The source owner owns the source commit/tree. `abyss-machine` owns artifact
classes, signatures, SBOM/provenance, registries, and admission policy. A route
admission receipt is not an artifact signature or a runtime-health proof.

### Stronger owner split

This part does not invent an artifact class for a source repository. If a
future installed package route needs artifact admission, it must first obtain
the exact `abyss-machine` policy class and admitted bundle evidence. Runtime
activation, Configs relinking, service operations, and semantic acceptance
remain explicit duties outside this source-only route.

### Inputs

`prepare` requires:

- an absolute clean Git source root;
- an exact 40-character `source_ref` and `source_tree`;
- an external JSON admission receipt with schema
  `abyss_stack_owner_source_deployment_admission_v1`;
- an absolute destination, release root, and optional receipt directory.

The admission receipt must bind the same owner, source, commit/tree, and
destination, be `admitted`, carry an unexpired validity window, and name one of
the explicit authority ceilings `disposable-source-package-canary` or
`installed-source-package-activation`.

### Outputs

The route emits and persists typed JSON receipts:

- `prepare`: `abyss_stack_owner_source_prepare_receipt_v1`;
- `activate`: `abyss_stack_owner_source_activate_receipt_v1`;
- `rollback`: `abyss_stack_owner_source_rollback_receipt_v1`;
- activation also persists an `abyss_stack_owner_source_activation_recovery_v1`
  journal before the destination switch.

The release is a self-contained Git clone under a sealed release directory. A
sidecar seal records the exact release path and Git ref/tree, the release-root
device/inode, and a content manifest. The manifest covers every regular file
and directory actually present, including ignored entries, records modes and
metadata, records symlink targets without following them, and rejects special
files. The release tree (including its Git metadata) is made read-only before
it can be referenced by a receipt. The destination is switched with a relative
symlink and `os.replace` only after the current predecessor and the sealed
release identity are rechecked immediately before the switch while a
non-blocking deployment lock is held. The lock coordinates cooperating route
writers; it cannot prevent a same-UID writer from replacing a prepared path.
Activation therefore verifies the release and destination again after the
switch. Live activation and `recover --action finalize` use the same
effect-bound contract: the route captures the temporary symlink's device/inode,
mode, target, link text, and a prepared-release owner token before the
successful `os.replace`, and persists that owner together with a committed
switch event before an activation receipt can be written. The event is
historical and explicitly carries
`current_destination_claim: false`; the receipt does not claim that a later
read of the destination is still current. A second release/seal/owner read is
kept as a defensive integrity fence before publication, but it is not the
atomicity proof. A writer after that fence is a later writer: the event receipt
remains truthful, while rollback and recovery require the durable owner token
and fail closed if its inode/link identity no longer matches. A privileged
actor that changes permissions or bypasses the filesystem boundary remains
outside this source-only guarantee.

The compared methods are deliberately separated. A cooperative `flock` or a
finite final recheck only coordinates or observes a pathname and cannot own an
arbitrary same-UID `os.replace`. A descriptor/rename-exchange or directory
transaction would still need a cross-file durable receipt transaction and would
not make a later pathname writer belong to this route. The selected method is
the atomic destination effect plus the pre-effect owner token, durable
`switch_complete` event, and explicit claim narrowing. Rollback adds a
pre-written deterministic displacement path and sequence, retains that path
through `rollback_switch_complete`, and restores a predecessor with a
sequence-bound link spelling. Both route-created paths carry exact
symlink/device/inode/mode/link identities in the durable displacement record;
pre-existing or replaced paths, including wrong-kind objects, are rejected.
The predecessor is restored only with its exact canonical sequence/token link
spelling. The owner and displacement records are carried through every retry;
claim narrowing without those recovery identities is not sufficient.

The durable journal records intent before the switch and permits deterministic
`recover --action finalize|rollback` after switch or receipt-write interruption.
If an interruption happens before the atomic switch owner can be durably
recorded (for example, before the destination directory fsync), recovery does
not infer ownership from target or seal and remains recovery-required.
Activation and rollback receipt references carry the journal binding, state
digest, operation, source, destination, release, predecessor, and admission;
cross-state references are rejected. Rollback records `rollback_intent` before
the predecessor switch and `rollback_switch_complete` before writing the
rollback receipt. Its compare-and-swap moves the observed destination to a
deterministic, pre-journaled displacement path with
`renameat2(RENAME_NOREPLACE)`, checks the moved inode/link identity, and
installs a predecessor only with another no-replace rename. The displacement
path is retained through the rollback-switch marker, so B1 (after
displacement), B2 (after predecessor install/cleanup), and B5 (inode reuse)
never require a fresh pathname inference. The destination parent is fsynced
after every destructive rename before durable state advances. Cleanup checks
the recorded exact object identity/kind before each unlink and fsyncs after
each deletion. B3 and B4 place a later writer after the rollback-switch marker
and during receipt publication; fences run before the receipt and again before
historical event publication. The second is the last current-state observation:
no post-publication finite fence is treated as ownership proof. Rollback then
emits `rollback_finalization` with method `historical-rollback-event-v1` and
`current_destination_claim: false`. A later writer can replace the destination
before return; the receipt and journal remain truthful historical records,
fresh reload accepts the typed event, and the later writer remains current. Any
directory-open/fsync or receipt persistence failure is a typed
`activation_recovery_required` result with the journal path; no completed
receipt is claimed. Rollback never deletes a release; it restores the
predecessor's logical target/identity (or the exact absent state) through a
unique owner spelling, rechecking its recorded ref, tree, clean mutable state,
and seal.

Ignored cache paths are excluded from Git's source identity check and are not
introduced by staging. If ignored content is already present in a release,
however, it is included in the sealed manifest and is covered by post-switch
verification. Tracked edits and non-ignored untracked content remain hard
failures; symlink targets are recorded without traversal and unsupported
special files are rejected.

### Must not claim

These receipts do not claim dependency installation, package parity,
artifact-signature admission, Configs projection, service/runtime activation,
runtime health, semantic acceptance, human acceptance, or Goal completion.

`--dry-run` performs the source, admission, destination, staging, and
same-filesystem preflight only and creates no route state.

### Validation

Focused tests use temporary Git repositories and disposable destinations. They
cover happy-path prepare/activate/rollback plus dirty source, wrong identity,
stale admission, stale staging, non-symlink destination, cross-device
preflight, concurrent lock, destination race, immediate pre-switch release
TOCTOU, tracked mutation after final verification, same-ref/tree replacement
with ignored poison after final verification, predecessor and activated release
ref/tree/clean tamper, ignored-cache packaging, manifest/symlink policy,
nested emitted schema instances, cross-state journal references,
directory-fsync ordering/failure, rollback receipt persistence failure, and
interruption/retry recovery at each activation boundary. Dedicated
interleavings cover the B1-B5 rollback crash matrix: a same-target writer after
durable displacement, after predecessor install/cleanup before the switch
marker, after the switch marker, during receipt publication, and after forced
inode reuse. They also cover same-target writers after ordinary and recovery
finalization event capture, owner replacement immediately after rollback
observation, pre-created predecessor paths, wrong-kind/path identity replay,
cleanup replacement, post-final-fence historical-event interleaving, mutation
after the shared post-switch verifier, and mutation during recovery
finalization; they assert seal/inode policy, owner-token non-reuse, exact
canonical spelling, fsync-before-journal ordering, historical events with no
current-destination claim, reload convergence, no receipt on ambiguous
rollback, and the durable journal state.
No live `/srv/AbyssOS` root is used by the tests.

```bash
scripts/aoa-deploy-owner-package --help
python -m pytest -q mechanics/runtime-lifecycle/parts/deployment-route/tests
```

### Next route

The next owner is the operator/deployment admission holder. It must review the
source receipts and, if applicable, run the separate `abyss-machine` artifact
trust loop before any installed activation. `abyss-stack` then owns the
explicit runtime activation and health proof; this part does not perform it.

## Commands

Preflight without mutation:

```bash
scripts/aoa-deploy-owner-package prepare \
  --owner-repo aoa-stats \
  --source-root /path/to/aoa-stats \
  --source-ref <40-char-commit> \
  --source-tree <40-char-tree> \
  --destination /srv/AbyssOS/aoa-stats \
  --admission-receipt /path/to/admission.json \
  --dry-run
```

The non-dry `prepare`, `activate`, and `rollback` commands are deliberately
operator-facing mutation commands. A source-only handoff should stop after
focused validation and preserve the receipts for the later holder.

If activation reports `activation_recovery_required`, use the recorded journal
as the only continuation point:

```bash
scripts/aoa-deploy-owner-package recover \
  --recovery-journal /absolute/path/to/activate-<prepare-operation-id>.recovery.json \
  --action finalize
```

Use `--action rollback` when the destination must return to the recorded
predecessor. Both actions are idempotent and remain source-only; neither
installs dependencies, starts services, or proves runtime health.
