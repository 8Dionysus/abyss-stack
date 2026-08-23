# Process containment part

This part owns the generic runtime boundary for one bounded invocation whose
process tree and temporary storage must have one owner.  It is deliberately
pytest-neutral.

Read the governed-execution package card and the root repository cards before
editing.  The part may expose a backend-neutral API and a Linux bubblewrap
backend, but callers must not depend on backend command-line flags.

The owner contract is fail-closed:

- a missing namespace or tmpfs capability returns `containment_unsupported`
  before the child command is started;
- no host pathname, PID, PGID, or quarantine name is a reclaim authority;
- only explicit read-only source/runtime mounts and explicit stdout/stderr
  export cross the boundary;
- namespace-init must reap and drain descendants before completion;
- export failure is `recovery_required` and leaves a visible owner recovery
  record when the requested export root is writable.

Part-local tests are deterministic and use synchronization primitives rather
than timing-only races.  Live kernel proof is separate evidence and must state
the exact backend and skipped capabilities.
