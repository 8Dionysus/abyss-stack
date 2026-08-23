# Process containment contract

Schema name: `abyss-stack-process-containment-v1`.

## Admission

Admission is an immutable capability check for one invocation.  It requires:

1. Linux user, PID, and mount namespace support.
2. An approved bubblewrap executable with a recorded SHA-256 digest.
3. Private tmpfs and procfs creation.
4. A regular source checkout and regular read-only runtime roots.
5. A private guest working directory and no forbidden external temp or pytest
   redirection variables.
6. No undeclared file descriptors beyond standard streams.
7. A private admission pipe is released only after the host same-UID probe;
   no external signal can release the namespace-init gate.
8. `PR_SET_DUMPABLE=0`, `PR_SET_NO_NEW_PRIVS`, disabled nested user namespaces,
   and an all-capabilities drop in namespace init.

Failure is visible as:

```json
{
  "status": "containment_unsupported",
  "reason": "...",
  "command_started": false
}
```

The adapter must not launch pytest after this result and must not invoke a
legacy cleanup path.

## Identity

The receipt binds a random invocation identity, profile/command/environment
digests, backend digest, backend pidfd start-time identity, the separate
host-side identity of namespace PID 1 used for admission, and user/mount/PID
namespace inode identities.  The namespace-init host identity is bound to the
backend controller's child relation, its start-time, and a pidfd probe. Numeric
PID and PGID values may appear as diagnostic facts, but never as ownership
authority.

## Lifecycle

Namespace init owns every descendant in its PID namespace.  It records the
main command result and start-time, reaps all waitable children, verifies an
empty PID-1 children list, and emits `drain_complete=true` only after both
checks succeed.  The outer controller waits through the backend pidfd and
`waitid(P_PIDFD, ...)`; no numeric PID wait is used.  Signals are sent with a
namespace-wide `kill(-1, signal)` broadcast; no numeric process-group ownership
is used.  A drain failure is an infrastructure failure and is never converted
into success by `ProcessLookupError`.

## Storage and export

The only temporary storage available to the guest is private tmpfs.  On normal
completion the backend exits and bubblewrap tears down that mount namespace.
The host controller does not remove a guest pathname.  Host output is an
explicit export destination supplied by the owner; export errors produce
`recovery_required`, a visible owner-controlled recovery lease, and a
`recovery-required.json` record when the requested root is writable.

The receipt reports mount evidence for `/tmp`, `/var/tmp`, `/dev/shm`, and
`/proc`, no forbidden hidden residue, and no live descendants at completion.
