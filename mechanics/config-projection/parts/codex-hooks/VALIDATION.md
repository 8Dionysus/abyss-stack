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
- unresolved/independent denial with role-first direction;
- typed `not_independent` local compatibility and unrelated-tool pass-through;
- malformed or missing context fail-closed behavior without invented identity;
- composition of the stack-owned adapter fragment without dropping existing
  native hook handlers.

These checks establish composition mechanics only. They do not establish Codex
trust, live hook invocation, owner-hook health, skill selection, memory use,
outcome, or benefit. A fresh-session live exercise is required to separate
installed source, Codex trust, hook execution, tool block/allow, and any later
owner classification or actor launch.
