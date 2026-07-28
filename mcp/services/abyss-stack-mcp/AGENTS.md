# AGENTS.md

Applies to `mcp/services/abyss-stack-mcp/`.

## Role

This package is the stack-owned runtime observation and plan-candidate access
plane accepted by `ABYSS-STACK-D-0087`. It reports evidence about direct owner
adapters. It is not a gateway and does not execute prepared plans.

## Read before editing

1. Repository root `AGENTS.md`
2. `mcp/AGENTS.md`
3. `mcp/services/AGENTS.md`
4. `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
5. This package `README.md`, `DESIGN.md`, and `docs/`

## Boundaries

- Keep read and candidate processes, tools, ports, credentials, and scopes
  disjoint.
- Runtime observations come from one explicit secret-free file; do not scan the
  workspace or infer owner acceptance.
- Candidate plans are immutable, content-addressed, short-lived, and always
  `execution_authorized=false`.
- Do not add runtime effects until a separate threat model, policy proof,
  approval contract, postcondition canary, and rollback proof are accepted.

## Validation

```bash
python mcp/services/abyss-stack-mcp/scripts/generate_stack_mcp_contracts.py --check
python mcp/services/abyss-stack-mcp/scripts/validate_stack_mcp.py
python -m pytest mcp/services/abyss-stack-mcp/tests -q
python mcp/services/_shared/build_http_auth_vendors.py --check
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
```

## Closeout

Report which plane changed, whether credential or host exposure moved, which
live observation was or was not checked, and whether any effect authority
changed.
