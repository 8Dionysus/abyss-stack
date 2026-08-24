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

The release is a self-contained Git clone under an immutable-by-identity
release directory. The destination is switched with a relative symlink and
`os.replace` only after the current predecessor identity is rechecked while a
non-blocking deployment lock is held. The durable journal records intent before
the switch and permits deterministic `recover --action finalize|rollback` after
switch or receipt-write interruption. Rollback never deletes a release; it
restores the exact predecessor symlink or the exact absent state, rechecking its
recorded ref, tree, and clean mutable state.

Ignored cache paths are excluded from Git's source identity check and are not
copied into a self-contained release. Tracked edits and non-ignored untracked
content remain hard failures; ignored content is never part of the immutable
release identity.

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
preflight, concurrent lock, destination race, predecessor and activated
release ref/tree/clean tamper, ignored-cache packaging, nested emitted schema
instances, malformed journals, and interruption/retry recovery at each
activation boundary. No live `/srv/AbyssOS` root is used by the tests.

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
