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

The cleanup boundary has a separate identity problem. A retained `O_PATH`
descriptor, a prior `stat`, and an immediate recheck all describe the object
that was observed, but `unlinkat`/`rmdir` still resolve a mutable directory
entry at their later syscall. The old child-entry path therefore admitted a
same-UID replacement between validation and destruction. The repair must bind
each object before destruction and must state what happens when the platform
cannot provide deletion by descriptor or when a mutator is outside the
invocation's containment set.

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
- Retain the namespace descriptor, scan the original parent for a renamed
  entry with the exact device/inode/type identity, and remove that entry by
  name. This can classify same-parent recovery, but a POSIX/Linux directory
  has no portable race-safe `rmdir`-by-fd primitive; using the recovered name
  would reintroduce a deletion race. The safe fallback is to clear only the
  retained inode through its descriptor and report the remaining link as a
  cleanup failure.
- Atomically quarantine each candidate with Linux `renameat2(RENAME_NOREPLACE)`
  and a fresh destination, open the moved destination with `O_PATH|O_NOFOLLOW`,
  and compare device/inode/type before doing anything destructive. This binds
  the object moved at the atomic instant, rejects destination collisions
  without overwriting them, and restores an unexpected candidate with another
  no-replace move or a fresh recovery name. A random name or `rename` without
  destination exclusion and identity validation is not sufficient.
- Drain the process groups created by this invocation before deleting a bound
  quarantine slot. `start_new_session` gives each process shard an explicit
  group; cleanup sends bounded `SIGTERM`/`SIGKILL`, reaps the leader, and fails
  closed if the group survives. This is the authority boundary for the final
  name-based `unlink`/`rmdir`, because Linux/Python exposes no unlink-by-fd
  primitive. A same-UID process not owned by the invocation cannot be fenced
  by this runner; a stronger process-isolation owner is required for that
  contract.
- Keep only retained-fd content reclamation and a visible failure when the
  owner namespace has already escaped its parent or a race binding cannot be
  recovered. This preserves data and avoids claiming that the retained inode
  makes an arbitrary mutable name safe to delete, but it intentionally leaves
  a tombstone for that failure case.
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
stack, fd-relative `listdir`, `O_PATH|O_NOFOLLOW` identity handles, and Linux
`renameat2(RENAME_NOREPLACE)` bindings. Before cleanup can destruct anything,
registered invocation-owned process groups are drained; a surviving group
raises a visible busy failure and no retry re-resolves its names. The outer
namespace is atomically moved from its public name to a fresh quarantine name
and identity-checked. Every child entry then follows the same boundary:
regular files and symlinks are moved without following them, directories are
moved and traversed through their retained fd, and each staged entry is moved
again to a fresh deletion slot and identity-checked before its final
`unlink`/`rmdir`. A no-replace destination collision never overwrites the
occupant. If the object at a quarantine or deletion destination is unexpected,
the candidate is moved back with no-replace semantics or published under a
fresh `.recovered-*` name; no destructive helper runs and the retry loop stops.

The final deletion slot is under the retained parent fd and is used only after
the invocation-owned mutator set has been drained. That containment is the
actual authority boundary for a syscall that still accepts a name. It is not a
mathematical guarantee against an unrelated same-UID process that already has
the parent or namespace fd: no available Linux/Python primitive can atomically
unlink an object by its retained fd. If that unowned actor is in scope, the
honest result is a stronger process-isolation owner handoff, not a claim of
race safety. When the binding itself fails, the implementation leaves the
candidate recoverable and reports failure; it never falls back to deleting a
new object through the old name.

The retained outer namespace descriptor remains the authority for link state:
ordinary uncontended cleanup reports success only after `fstat` proves
`st_nlink == 0`. If the original namespace name is missing or replaced while
the retained inode remains linked, classification may inspect exact identity
without deleting the recovered name; safe fd-only content reclamation may
clear owned payloads, but the remaining link is a visible failure. A
same-parent rename, an inode moved outside the retained parent, an ancestor
swap, or an original-name replacement therefore preserves the changed
candidate and cannot produce false success. Partial diagnostics are created
with an exclusive no-follow open against the retained parent; if their write
or close fails, only the just-created diagnostic identity is quarantined into
the owner namespace and the same binding rules protect its cleanup. No
recovery or cleanup retry re-stats a mutable candidate after a race result.
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
outside the authority boundary. Atomic no-replace quarantine supplies the
missing identity binding at each mutable pathname boundary, while the drained
process-group set supplies the only available authority for the final
name-based destruction. The explicit rejection of a user basetemp preserves
the invariant even when callers provide extra pytest arguments. Rejecting
pytest's recursive argument-file expansion is safer than cloning a
version-sensitive parser, while clearing config `addopts` preserves ordinary
target, nodeid, and plugin options. The diagnostic is written only for a
namespace this invocation created, so a failed cleanup is classified without
scanning or deleting legacy tombstones. The design keeps ordinary completed
runs clean and makes every unsupported or uncontained destruction boundary
visible instead of silently consuming unrelated data.

## Consequences

- Positive: new canonical-lane invocations do not create pytest's shared
  numbered temp root or its repeated tombstones.
- Positive: each shard retains independent pytest temp state and cleanup is
  limited to its own namespace.
- Positive: an ancestor rename or symlink replacement cannot redirect cleanup or
  diagnostic publication, and mode-000 directories are repaired without
  chmod'ing payload files.
- Positive: a retained inode cannot be reported as removed merely because its
  original name disappeared; exact same-parent renames and moved/replaced
  namespaces are classified from the retained parent and fail visibly when no
  race-safe directory unlink primitive exists.
- Positive: regular-file, symlink, child-directory, outer-namespace,
  deletion-slot, diagnostic, destination-collision, and rollback-collision
  paths all use an atomic identity bind before destruction; unexpected
  candidates remain at an original or recovery name and do not produce false
  success.
- Positive: invocation-owned subprocess groups are explicitly drained before
  cleanup, so a surviving background mutator cannot continue racing the
  deletion slots; a group that cannot be drained produces a visible cleanup
  failure.
- Positive: direct, environment, config, and parser-expanded argument paths
  cannot redirect the owner basetemp; rejected expansion syntax fails before
  pytest can touch a caller-owned path.
- Tradeoff: the wrapper owns a small amount of process lifecycle bookkeeping,
  and direct pytest commands outside this canonical lane retain their normal
  upstream behavior. The fd-relative/quarantine contract is strongest on
  Linux with `renameat2`; unsupported platforms fail visibly instead of
  weakening ownership. A robust-deletion failure intentionally leaves a
  classified owner diagnostic and fails the lane so the state is visible. An
  unregistered same-UID mutator remains outside the guarantee and needs
  stronger process isolation. This canonical lane intentionally does not
  support pytest `@file` arguments and owns the config `addopts` setting.
- Follow-up: independent review must validate the source diff and select an
  owner-approved source-to-Configs deployment transaction.

## Source surfaces

- `scripts/run_pytest_lane.py`
- `tests/test_validation_command_authority.py`
- `docs/validation/COMMAND_AUTHORITY.md`
- `docs/validation/VALIDATOR_TOPOLOGY.md`

## Follow-up route

The independent reviewer should confirm the Linux/Python primitive comparison,
the atomic binding and recovery invariants, process-group drain evidence, the
file/symlink/directory/outer/diagnostic swap barriers, uncontended cleanup,
link-state, same-parent rename, replacement, moved-parent, lookup-race,
cleanup-success, and cleanup-failure-visibility tests. Re-run the focused and
full validation lanes on Python 3.12 and the actual serial/process runner
paths. The reviewer must also decide whether the documented unregistered
same-UID impossibility boundary requires a stronger process-isolation owner;
runtime activation remains unclaimed until that route has a precise rollback
artifact and an exact landed source ref.
