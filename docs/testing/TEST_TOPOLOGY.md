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
uses at most four process-isolated workers over 32 deterministic file-aware
shards. One baseline collection and each child's observed manifest prove an
exact disjoint union before the aggregate can pass. Use:

```bash
ABYSS_STACK_TEST_SCHEDULER=serial python scripts/ci_gate.py --mode tests
```

as the exact rollback and independent sequential oracle. The scheduler may
change execution order only. Duration hints cannot change membership. It does
not skip, lose, retry, or reinterpret failures. It replays failed shard logs
after the aggregate so an early traceback remains visible in bounded log tails.

Expensive transport setup may be stratified from semantic assertions only
inside the owning test harness. The external Codex suite keeps named exact
preflight, nested-sandbox, credential-refusal, process-cleanup, and complete
lifecycle sentinels on the production implementation. Tests whose claim is
instead about lifecycle state, reports, evidence, or authority use a
contract-shaped successful preflight double bound only to that fixture runtime;
the forked worker inherits it through the same admission and revalidation call
sites. There is no production switch for the double. A test whose expected
result depends on live preflight must explicitly select the exact fixture path.

Tests of local Agent OS and governed review-packet semantics provide an
explicit deterministic advisory trace. They must not call a deployed advisory
endpoint and pass through its timeout fallback; live service integration is a
separate opt-in evidence lane.
