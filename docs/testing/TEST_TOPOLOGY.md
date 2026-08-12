# Test Topology

`abyss-stack` tests protect source-checkout runtime contracts. They should stay
deterministic, public-safe, and explicit about which owner surface failed.

## Homes

| Home | Scope | Current posture |
|---|---|---|
| `tests/` | root integration contracts | blocking default pytest lane |
| `mechanics/*/parts/*/tests/` | mechanic part-local contracts | blocking default pytest lane |
| `mcp/services/*/tests/` | MCP service package contracts | blocking default pytest lane and service-local lanes |
| `mechanics/*/legacy/*/tests/` | archived provenance tests | not collected by default; run explicitly only for archive review |

## Families

| Family | Protects | Lane |
|---|---|---|
| root runtime contracts | compose, schemas, route cards, validators, parity behavior | tests, release |
| mechanic part-local contracts | mechanic-owned wrappers, schemas, examples, status, federation, repair, pilots | tests, mechanics-part-local, release |
| MCP service contracts | service-local access-plane boundaries and package validators | mcp-services, tests, release |
| archived provenance contracts | preserved archived schema/example behavior | explicit archive-review only |
| topology authority tests | validation, script, and test inventories plus command authority | source-fast, tests |

## Rules

- Tests are not command authority. They may assert lane wiring, but full
  command sequences live in `docs/validation/validation_lanes.json`.
- Default tests must not require live deployed runtime state, private captures,
  host-local model downloads, secrets, or destructive actions.
- Legacy test paths must stay out of default discovery and default inventory.
- Broad release behavior should be tested through lane-composition assertions,
  not by replaying the full release gate inside an ordinary unit test.

## Full-Suite Scheduler

The `tests` and `release` lanes keep the complete default pytest selection and
route only its scheduling through `scripts/run_pytest_lane.py`. Automatic mode
admits exact `pytest-xdist==3.8.0` with four workers and `worksteal`; if that pin
is absent or different, it runs the same selection serially. Use:

```bash
ABYSS_STACK_TEST_SCHEDULER=serial python scripts/ci_gate.py --mode tests
```

as the exact rollback and independent sequential oracle. The scheduler may
change execution order only. It does not skip, deselect, shard away, retry, or
reinterpret failures.
