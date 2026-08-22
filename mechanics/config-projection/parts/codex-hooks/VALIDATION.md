# Codex hook composition validation

Run from the repository root:

```bash
python -m pytest -q mechanics/config-projection/parts/codex-hooks/tests
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

Focused tests cover:

- native standalone plus owner-envelope coexistence;
- fragment, group, and handler order;
- exact binding and metadata removal;
- unsupported events/handlers/fields and event matcher constraints;
- unresolved placeholders, unsafe bindings, and duplicate handlers;
- `SessionEnd` timeout ceiling;
- mode-`0600` atomic write, private backup, receipt validation, and rollback;
- content-minimized receipts with no raw source or binding path;
- read-only exact-output comparison.
- exact Codex `PreToolUse` agent-tool recognition and SDK routing;
- session-owned base relay copies only safe attempt coordinates and writes
  one event-keyed context atomically; unknown namespace members leave no
  unclaimable context;
- canonical `spawn_agent`, flattened v1/v2 identities, observed compatibility
  aliases, and unknown-name fail-closed matcher coverage;
- unresolved/independent denial with role-first direction;
- typed `not_independent` local compatibility and unrelated-tool pass-through;
- bounded oversized-context reads, exact safe attempt-key binding,
  claim-before-read single-use typed context consumption, concurrent producer
  isolation, bounded relay/adapter concurrency waiting, and selected SDK-root
  verification;
- inner timeout denial before the longer native hook timeout;
- malformed or missing context fail-closed behavior without invented identity;
- composition of the stack-owned adapter fragment without dropping existing
  native hook handlers, with explicit context-directory and SDK-source
  bindings.
- clean-source content-addressed release materialization, manifest closure,
  immutable committed-blob source identity, stale-release rejection, active
  state preflight, native/output distinct-path alias rejection, unique receipt
  reservation, read-only release finalization, durable release-tree and
  receipt-directory sync, prior composition-receipt restoration, and installer
  rollback when its active receipt cannot be written.

These checks establish composition mechanics only. They do not establish Codex
trust, live hook invocation, owner-hook health, skill selection, memory use,
outcome, or benefit. A fresh-session live exercise is required to separate
installed source, Codex trust, hook execution, tool block/allow, and any later
owner classification or actor launch. The relay tests additionally establish
only transport from an externally supplied typed base; they do not prove that a
session owner published a truthful base.
