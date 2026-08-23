# Process containment

`process-containment` is the generic runtime owner for a single bounded
invocation.  It owns the process and storage boundary; adapters own command
selection and their own semantic receipts.

## Contract shape

`contained_invocation.py` accepts a `ContainmentSpec` containing an explicit
source root, read-only runtime roots, command, guest working directory, safe
environment, profile ID, and optional export root.  The public result is
backend-neutral and reports one of `completed`, `containment_unsupported`,
`recovery_required`, or `infrastructure_failure`.

The current approved Linux backend is bubblewrap.  Its implementation is an
internal capability of this part, not a public adapter contract.

## Boundary

The backend creates a private user, PID, and mount namespace, mounts private
tmpfs at `/tmp`, `/var/tmp`, and `/dev/shm`, mounts a private `/proc`, disables
nested user namespaces, drops capabilities after setup, and sets
`PR_SET_DUMPABLE=0` and `PR_SET_NO_NEW_PRIVS` in namespace init.  Source and
runtime roots are explicit read-only binds.  No writable host bind, host temp
directory, private namespace fd, or temp-directory fd is passed to the child.

Namespace init is PID 1.  It launches the requested command, forwards
termination using a namespace-wide broadcast, reaps ordinary and reparented
descendants, and performs an explicit drain before it emits its receipt.  The
host controller releases it through an owner-controlled pipe only after the
same-UID procfs/namespace/fd probe passes.  The probe targets the host identity
of the private PID-1 child, not bubblewrap's host-facing wrapper; that target
is bound to the wrapper's child relation, start time, and pidfd probe.  The
outer controller waits on a pidfd with `waitid(P_PIDFD, ...)` and verifies the
immutable start-time identity of the backend process.

Successful reclaim is namespace teardown.  The part never calls `unlink` or
`rmdir` for invocation temporary storage.  Logs and receipts are exported only
to an explicit owner path or to the caller's output streams.

## Portability

The Linux profile is the only profile currently implemented.  Other hosts and
Linux hosts without all admitted capabilities return a structured
`containment_unsupported` result before the command starts.  There is no PGID,
pathname-cleanup, percentage, or legacy fallback.

## Validation

Run the part-local tests with:

```bash
python -m pytest -q mechanics/governed-execution/parts/process-containment/tests
```

Those tests include mocked fail-closed admission, identity and receipt
parity, child reaping, setsid/double-fork fixtures, retained descriptors,
read-only mount construction, and teardown-only reclaim assertions.  A live
test is marked separately when the host cannot admit user/PID/mount namespaces.
