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
switch. Live activation and `recover --action finalize` enter the same locked
finalization admission: the post-switch verifier is followed by a second
destination/seal snapshot and a destination inode/link identity token. That
token is durably bound to the recovery journal before an activation receipt
can be written. Any content, root-inode, or destination drift at either read
causes the same durable rollback to the predecessor and no activation receipt.
A privileged actor that changes permissions or bypasses the filesystem
boundary remains outside this source-only guarantee.

The durable journal records intent before the switch and permits deterministic
`recover --action finalize|rollback` after switch or receipt-write interruption.
Activation and rollback receipt references carry the journal binding, state
digest, operation, source, destination, release, predecessor, and admission;
cross-state references are rejected. Rollback records `rollback_intent` before
the predecessor switch and `rollback_switch_complete` before writing the
rollback receipt. Its compare-and-swap moves the observed destination to a
displaced path with `renameat2(RENAME_NOREPLACE)`, checks the moved inode/link
identity, and installs a predecessor only with another no-replace rename. A
same-UID writer that replaces the destination between observation and commit
is preserved and the route fails closed with recovery required; it is never
unlinked or overwritten. Any directory-open/fsync or receipt persistence
failure is a typed `activation_recovery_required` result with the journal path;
no completed receipt is claimed. Rollback never deletes a release; it restores
the exact predecessor symlink or the exact absent state, rechecking its
recorded ref, tree, clean mutable state, and seal.

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
directory-fsync failure, rollback receipt persistence failure, and
interruption/retry recovery at each activation boundary. Dedicated
interleavings cover mutation after the shared post-switch verifier, mutation
during recovery finalization, and a same-target writer during rollback CAS;
they assert seal/inode policy, no receipt claim, and the durable journal state.
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
