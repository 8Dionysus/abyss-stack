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

These checks establish composition mechanics only. They do not establish Codex
trust, live hook invocation, owner-hook health, skill selection, memory use,
outcome, or benefit.
