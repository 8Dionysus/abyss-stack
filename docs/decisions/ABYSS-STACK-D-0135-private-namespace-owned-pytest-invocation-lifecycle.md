# Private Namespace-Owned Pytest Invocation Lifecycle

- Decision ID: ABYSS-STACK-D-0135
- Status: proposed
- Date: 2026-08-22
- Owner surface: `mechanics/governed-execution/parts/process-containment/`

## Index Metadata

- Original date: 2026-08-22
- Surface classes: runtime process containment, validation workflow, storage boundary
- Stack lanes: governed execution, validation, tests
- Mechanic parents: governed-execution
- Guard families: namespace admission, descendant drain, tmpfs teardown, fail-closed portability
- Posture: proposed rationale pending exact-head live proof

## Context

The previous pytest lifecycle used mutable host temporary pathnames and numeric
process-group ownership.  Independent review showed that a same-UID actor could
replace the final deletion slot after identity validation, and that PID/PGID
reuse, `setsid`, and double-fork descendants could escape the registered
ownership set.  Creation rollback could also hide recovery residue.

The accepted architecture requires one owner for both the invocation process
tree and its temporary storage while preserving D-0120 collection, serial, and
4x32 shard semantics.

## Options considered

- Keep fd-relative quarantine cleanup and strengthen rechecks.  This still
  leaves the final mutable-name race and cannot make host pathname deletion a
  safe ownership boundary.
- Use only cgroup v2 or a systemd transient unit.  These can improve process
  membership but do not make shared host storage private and are not portable
  across the admitted validation hosts.
- Use a dedicated subreaper without a private mount namespace.  This can drain
  some descendants but cannot reclaim temporary bytes by owner teardown or
  close same-UID host pathname/fd mutation.
- Use a private user+PID+mount namespace with private tmpfs and namespace-init
  drain.  This closes the process/storage ownership boundary when capability
  admission passes and fails closed otherwise.

## Decision

The generic process-containment part owns a backend-neutral invocation API.  The
approved Linux implementation uses bubblewrap to create a private user, PID,
and mount namespace, explicit read-only source/runtime mounts, private tmpfs
for temporary paths, private procfs, dumpability/no-new-privilege controls,
and namespace-init PID-1 reaping and drain.  The outer controller waits on a
pidfd plus immutable start-time evidence.  Namespace teardown, not host
pathname deletion, reclaims invocation temporary storage.

`run_pytest_lane.py` consumes this API as a thin adapter.  It performs command
authority and D-0120 selection/partitioning inside one containment instance;
it does not own kernel launch flags, storage cleanup, PGID registration, or
host quarantine names.

Unsupported hosts return `containment_unsupported` before pytest starts.  An
explicit export failure returns `recovery_required` with a visible recovery
record where the owner export root permits it.  No legacy cleanup, percentage
launch restriction, or fd-only tombstone success path is allowed.

## Rationale

One namespace owns both descendants and tmpfs, so `setsid`, double-fork, nested
trees, and retained temp descriptors remain inside the same lifecycle.  PID-1
drain supplies an ownership proof that a numeric leader or PGID cannot provide.
Private tmpfs makes complete reclaim a namespace teardown operation and removes
the final host-name substitution race.  Explicit mounts and environment
admission keep source/runtime visibility reviewable and make unsupported kernel
posture visible before a test starts.

The adapter boundary preserves D-0120's exact baseline manifest, disjoint
assignment, observed-selection receipt, aggregate result, serial rollback, and
4-worker/32-shard scheduler.  The generic owner remains reusable by future
runtime adapters without importing the external-Codex host-specific profile.

## Consequences

- Positive: process and temporary storage ownership have one teardown boundary.
- Positive: unsupported capability posture fails closed before user code runs.
- Positive: logs, statuses, and receipts cross the boundary only through an
  explicit export or the caller's output streams.
- Tradeoff: the canonical profile is Linux-only until another backend proves
  the same contract; live kernel proof remains separate from deterministic
  source tests.
- Tradeoff: source/runtime roots must be declared and mounted read-only, and
  host-owned environment redirections are rejected.
- Follow-up: keep this record proposed until the exact pushed heads complete the
  architecture report's live adversarial proof; then the decision owner reviews
  status and derived surfaces.

## Source surfaces

- `mechanics/governed-execution/parts/process-containment/CONTRACT.md`
- `mechanics/governed-execution/parts/process-containment/contained_invocation.py`
- `mechanics/governed-execution/parts/process-containment/namespace_launcher.py`
- `mechanics/governed-execution/parts/process-containment/tests/`
- `scripts/run_pytest_lane.py`
- `docs/validation/validation_lanes.json`
- `docs/decisions/ABYSS-STACK-D-0120-schedule-full-pytest-with-bounded-work-stealing.md`

## Follow-up route

The source writer records exact-head deterministic and live proof in the actor
receipts and hands both stacked PR heads to an independent reviewer.  The
governed-execution owner may promote this decision only after capability,
same-UID, drain, teardown, export-failure, unsupported-host, and D-0120 parity
evidence are all reviewed.
