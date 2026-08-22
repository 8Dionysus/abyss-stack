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
- Guard families: temporary namespace isolation, pytest argument authority, fd ownership, no-follow cleanup, upstream pytest lifecycle, source/runtime boundary
- Posture: proposed invocation-owned temp and argument-authority invariants pending independent review

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

Pytest's parser has additional caller-controlled argument sources beyond the
wrapper's direct argv. Its supported `@file` syntax expands recursively before
option parsing, `PYTEST_ADDOPTS` is prepended using shell-style splitting, and
configured `addopts` is also prepended. Since the last parsed `--basetemp`
wins, moving the owner's option earlier or later alone cannot establish the
invariant. A direct `-o/--override-ini addopts=...` can also reintroduce an
option stream after the owner's command construction.

## Options considered

- Keep pytest's default numbered root and rely on its tombstone cleanup. This
  preserves upstream behavior but permits repeated tombstone accumulation.
- Configure one static shared `--basetemp`. This avoids numbered-root
  tombstones but violates parallel isolation and permits reuse across runs.
- Scan and remove `pytest-of-*`, `garbage-*`, or other historical directories
  from the runner. This would duplicate upstream semantics and claim authority
  over legacy data or arbitrary temporary data.
- Allocate one fresh owner-owned namespace per runner invocation, derive its
  parent from the upstream/runtime environment, pass an uncreated child
  basetemp beneath it as `--basetemp`, and clean only the outer namespace after
  the process ends with bounded explicit retries. This preserves isolation
  while allowing pytest's normal basetemp setup to replace its child and avoids
  the numbered-root tombstone path for new lane work.
- Allocate the namespace with a retained parent descriptor and use a
  path-following recursive remover. This makes creation fd-relative, but still
  permits an ancestor replacement to redirect cleanup and diagnostics.
- Move the owner `--basetemp` option within the generated command and allow
  pytest to expand all other sources. This leaves recursive `@file`, environment,
  config, and last-option behavior outside the runner's proof.
- Reimplement pytest's complete argument-file and configuration parser in the
  runner. This could inspect more syntax, but would create a second parser
  authority that can drift from the installed pytest version.
- Reject the parser-expansion surface before launch, validate
  `PYTEST_ADDOPTS` with the same `shlex` tokenization pytest uses, clear
  configuration `addopts` with an owner option, reject direct addopts authority
  overrides, and place the owner option before direct caller arguments. This
  keeps the proof in one semantic authority surface and fails closed for
  unsupported expansion syntax.

## Decision

The canonical `run_pytest_lane.py` allocates a fresh outer owner namespace for
serial execution, exact collection, and every parallel shard. It opens the
selected parent with `O_DIRECTORY|O_NOFOLLOW` and creates that owner namespace
directly with `mkdir(..., dir_fd=parent_fd)`. The retained binding carries the
parent and owner descriptors plus their object identities. The context yields
an uncreated `pytest-basetemp` child `Path` beneath the owner namespace, which
pytest may replace during its normal setup; cleanup never re-opens that display
path and instead cleans the retained outer owner handle. Every generated pytest
command receives that typed child path as `--basetemp`, and user-supplied
reusable `--basetemp` arguments are rejected.

The same runner-owned argument-authority validator is applied at the public
entrypoint, serial command builder, collection command builder, process shard
builder, and subprocess environment construction. It rejects both direct
`--basetemp` spellings, every `@` argument-file token (including relative and
nested files), direct addopts overrides, unsafe `PYTEST_ADDOPTS` tokens, an
environment end-of-options marker that would precede the owner option, and
malformed environment shell text. The runner does not open or partially parse
argument files. Generated commands clear pytest config `addopts` after pytest's
prepended environment/config sources and place the fresh owner `--basetemp`
before direct caller arguments, so a direct `--` cannot make the owner option
positional. Rejected input returns before any pytest subprocess or owner
namespace is started.

Cleanup is an explicit bounded retry lifecycle using an iterative post-order
stack, fd-relative `listdir`, `O_PATH|O_NOFOLLOW` identity handles, no-follow
identity checks, `unlink`, and `rmdir`. Child completion reopens its anchored
`..` parent, verifies that parent identity, and removes the exact original
child name without retaining one descriptor per ancestor. Symlink entries are
removed as names and never traversed; a platform without the identity-handle
primitive fails visibly rather than weakening the stat/delete boundary.
Directory permission repair adds only owner
read/write/search bits to a checked directory: it uses `fchmod` when an
ordinary no-follow directory fd is available, a platform-provided
`dir_fd`/`follow_symlinks=False` chmod when supported, or Linux `O_PATH` plus
the opened object's `/proc/self/fd` reference for mode-000 directories. A
platform without a safe capability fails visibly rather than following a
pathname. If removal still fails, the diagnostic is created with a relative
exclusive open against the retained parent; partial-write or close failure
removes only the just-created diagnostic identity, while collisions survive.
Candidate exhaustion is normalized at the runner boundary. Serial,
collection, and shard handles are independent, close-on-exec, and closed on
all success/failure paths.

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
isolated. The immutable parent handle keeps ancestor rename/symlink replacement
outside the authority boundary, while identity checks prevent a replaced name
from being deleted. The explicit rejection of a user basetemp preserves the
invariant even when callers provide extra pytest arguments. Rejecting pytest's
recursive argument-file expansion is safer than cloning a version-sensitive
parser, while clearing config `addopts` preserves ordinary target, nodeid, and
plugin options. The diagnostic is
written only for a namespace this invocation created, so a failed cleanup is
classified without scanning or deleting legacy tombstones.

## Consequences

- Positive: new canonical-lane invocations do not create pytest's shared
  numbered temp root or its repeated tombstones.
- Positive: each shard retains independent pytest temp state and cleanup is
  limited to its own namespace.
- Positive: an ancestor rename or symlink replacement cannot redirect cleanup or
  diagnostic publication, and mode-000 directories are repaired without
  chmod'ing payload files.
- Positive: direct, environment, config, and parser-expanded argument paths
  cannot redirect the owner basetemp; rejected expansion syntax fails before
  pytest can touch a caller-owned path.
- Tradeoff: the wrapper owns a small amount of process lifecycle bookkeeping,
  and direct pytest commands outside this canonical lane retain their normal
  upstream behavior. The fd-relative contract is strongest on POSIX platforms
  exposing the required no-follow operations; unsupported platforms fail
  visibly instead of weakening ownership. A robust-deletion failure
  intentionally leaves a classified owner diagnostic and fails the lane so the
  state is visible. This canonical lane intentionally does not support pytest
  `@file` arguments and owns the config `addopts` setting.
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
