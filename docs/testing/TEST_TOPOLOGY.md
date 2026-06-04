# Test Topology

`abyss-stack` tests protect source-checkout runtime contracts. They should stay
deterministic, public-safe, and explicit about which owner surface failed.

## Homes

| Home | Scope | Current posture |
|---|---|---|
| `tests/` | root integration contracts | blocking default pytest lane |
| `mechanics/*/parts/*/tests/` | mechanic part-local contracts | blocking default pytest lane |
| `mcp/services/*/tests/` | MCP service package contracts | blocking default pytest lane and service-local lanes |
| `mechanics/*/legacy/*/tests/` | preserved provenance tests | currently collected; must stay explicitly labeled |

## Families

| Family | Protects | Lane |
|---|---|---|
| root runtime contracts | compose, schemas, route cards, validators, parity behavior | tests, release |
| mechanic part-local contracts | mechanic-owned wrappers, schemas, examples, status, federation, repair, pilots | tests, mechanics-part-local, release |
| MCP service contracts | service-local access-plane boundaries and package validators | mcp-services, tests, release |
| legacy provenance contracts | preserved archived schema/example behavior | tests, release, provenance-labeled |
| topology authority tests | validation, script, and test inventories plus command authority | source-fast, tests |

## Rules

- Tests are not command authority. They may assert lane wiring, but full
  command sequences live in `docs/validation/validation_lanes.json`.
- Default tests must not require live deployed runtime state, private captures,
  host-local model downloads, secrets, or destructive actions.
- A legacy test path in default discovery must have an inventory entry that
  explains why it is still active.
- Broad release behavior should be tested through lane-composition assertions,
  not by replaying the full release gate inside an ordinary unit test.
