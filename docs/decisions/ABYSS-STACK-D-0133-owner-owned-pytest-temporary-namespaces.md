# Owner-Owned Pytest Temporary Namespaces

- Decision ID: ABYSS-STACK-D-0133
- Status: proposed
- Date: 2026-08-21
- Owner surface: `scripts/run_pytest_lane.py`

## Index Metadata

- Original date: 2026-08-21
- Surface classes: validation workflow, test scheduler, temporary lifecycle
- Stack lanes: validation, tests, release
- Mechanic parents: none
- Guard families: temporary namespace isolation, upstream pytest lifecycle, source/runtime boundary
- Posture: proposed invocation-owned temp invariant pending independent review

## Context

The canonical full-test lane runs one collection invocation and multiple
process-isolated child invocations. Without an explicit basetemp, installed
pytest owns a numbered user root and its generic cleanup path can leave a
tombstone when removal fails. A fixed shared basetemp would avoid the numbered
root but would make concurrent invocations share mutable test state and would
silently change the invocation lifecycle.

The repair must remain independent of one incident's user, date, UUID,
worktree, or absolute path. It must also leave capacity policy and legacy
tombstone cleanup with their existing owners. A silent cleanup failure is not
an acceptable invocation lifecycle: an ignored removal error can make a
current owner namespace look complete while leaving its state behind.

## Options considered

- Keep pytest's default numbered root and rely on its tombstone cleanup. This
  preserves upstream behavior but permits repeated tombstone accumulation.
- Configure one static shared `--basetemp`. This avoids numbered-root
  tombstones but violates parallel isolation and permits reuse across runs.
- Scan and remove `pytest-of-*`, `garbage-*`, or other historical directories
  from the runner. This would duplicate upstream semantics and claim authority
  over legacy data or arbitrary temporary data.
- Allocate one fresh owner-owned namespace per runner invocation, derive its
  parent from the upstream/runtime environment, pass it as `--basetemp`, and
  clean only that namespace after the process ends with bounded explicit
  retries. This preserves isolation while avoiding the numbered-root tombstone
  path for new lane work.

## Decision

The canonical `run_pytest_lane.py` allocates a fresh temporary namespace for
serial execution, exact collection, and every parallel shard. The parent is
selected from `PYTEST_DEBUG_TEMPROOT` and `TMPDIR`, with the standard tempfile
fallback when neither configured parent is usable. Every generated pytest
command receives its typed namespace as `--basetemp`; user-supplied reusable
`--basetemp` arguments are rejected. The runner removes each namespace through
an explicit bounded retry lifecycle. If removal still fails, it writes a
namespace-specific owner diagnostic beside that namespace and returns a
visible cleanup failure; it never silently relies on ignored cleanup errors.

The scheduler's manifest/log workspace remains separate and is never used as a
pytest basetemp. The runner performs no tombstone matching, capacity check,
storage-percentage gate, concurrency reduction, throttling, backpressure, or
legacy cleanup. Installed upstream pytest remains authoritative for tombstone
semantics; the runner cleans only namespaces it created for the current
invocation.

## Rationale

The route uses the upstream-supported basetemp boundary and the machine's
existing runtime environment rather than encoding a host incident. A unique
directory per process makes collection, serial execution, and shards mutually
isolated. Owner-bounded cleanup is precise and cannot delete an unrelated
temporary tree. The explicit rejection of a user basetemp preserves the
invariant even when callers provide extra pytest arguments. The diagnostic is
written only for a namespace this invocation created, so a failed cleanup is
classified without scanning or deleting legacy tombstones.

## Consequences

- Positive: new canonical-lane invocations do not create pytest's shared
  numbered temp root or its repeated tombstones.
- Positive: each shard retains independent pytest temp state and cleanup is
  limited to its own namespace.
- Tradeoff: the wrapper owns a small amount of process lifecycle bookkeeping,
  and direct pytest commands outside this canonical lane retain their normal
  upstream behavior. A robust-deletion failure intentionally leaves a
  classified owner diagnostic and fails the lane so the state is visible.
- Follow-up: independent review must validate the source diff and select an
  owner-approved source-to-Configs deployment transaction.

## Source surfaces

- `scripts/run_pytest_lane.py`
- `tests/test_validation_command_authority.py`
- `docs/validation/COMMAND_AUTHORITY.md`
- `docs/validation/VALIDATOR_TOPOLOGY.md`

## Follow-up route

The independent reviewer should confirm the uniqueness, cleanup-success, and
cleanup-failure-visibility tests, re-run the focused validation lane, and
decide whether the broad documented `scripts/` Configs projection is safe for
a separate deployment transaction. Runtime activation remains unclaimed until
that route has a precise rollback artifact and an exact landed source ref.
