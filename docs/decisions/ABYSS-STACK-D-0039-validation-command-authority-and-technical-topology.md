# Validation Command Authority And Technical Topology

- Decision ID: ABYSS-STACK-D-0039
- Status: accepted
- Date: 2026-06-03
- Owner surface: `docs/validation/`, `docs/testing/`, `scripts/validation_lanes.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: docs route, generated/readout, validation guard
- Stack lanes: source checkout, runtime mechanics, docs and routes, decision lane
- Mechanic parents: cross-mechanic
- Guard families: release/tooling, validation lane
- Posture: accepted technical-topology foundation

## Context

`abyss-stack` had accumulated the same pressure seen in sibling AoA refactors:
validators, tests, scripts, workflow commands, and release checks were all
growing as one technical layer, but without one explicit authority map.

The most visible symptom was the large `scripts/validate_stack.py`, but that
file is not the whole problem. The repository also has root operator wrappers
that sync into deployed `Configs/scripts/`, service-local MCP validators, many
mechanic part-local tests, generated diagnostic and decision read models, a
release gate with inline command storage, and a GitHub workflow with duplicated
shellcheck command lists.

Splitting the large validator before naming command authority and inventory
coverage would make the next shape harder to review. The first durable move is
to expose which surface owns a command, script, validator, test, side effect,
lane, and failure route.

## Options considered

- Split `scripts/validate_stack.py` immediately into modules.
- Move only GitHub workflow commands into a helper script.
- Add validation/testing/script topology, inventories, a lane manifest, a lane
  loader, and topology tests before the validator body split.

## Decision

Create `docs/validation/` as the validation command-authority and topology
district:

- `COMMAND_AUTHORITY.md`
- `VALIDATOR_TOPOLOGY.md`
- `SCRIPT_TOPOLOGY.md`
- `validation_lanes.json`
- `validator_inventory.json`
- `script_inventory.json`

Create `docs/testing/` as the testing topology district:

- `TEST_TOPOLOGY.md`
- `test_inventory.json`

Use `docs/validation/validation_lanes.json` as the canonical command manifest.
`scripts/validation_lanes.py` loads the manifest, `scripts/ci_gate.py` executes
named lanes, and `scripts/release_check.py` remains the release entrypoint plus
synthetic/live Configs parity stabilizer while reading its release command
sequence from the manifest.

Keep the initial inventories descriptive rather than executable. They record
owners, lanes, side effects, CI inclusion, focused test targets, dispositions,
and failure routes. Command sequences stay in the lane manifest.

## Rationale

`abyss-stack` is a runtime substrate, so its script topology is stronger and
riskier than a normal helper folder. Root scripts are stable operator commands
and are mirrored into deployed `Configs/scripts/`; they need side-effect and
source/runtime posture visible before implementation bodies move.

Tests also need an explicit owner map because root tests, mechanic part-local
tests, MCP service tests, and currently collected legacy provenance tests all
join the default pytest lane. Without a test inventory, default discovery can
quietly promote preserved legacy evidence into an unlabeled hard gate.

The manifest-backed lane shape keeps workflow YAML, release helpers, tests, and
route cards from becoming separate command authorities. It also gives the next
validator split a stable destination: each extracted module should match one
owner surface and update the validator inventory.

## Consequences

- Positive: command authority is visible and testable.
- Positive: `release_check.py` keeps parity stabilization without owning an
  inline release command list.
- Positive: scripts and tests now have machine-readable owner and disposition
  maps before future splits.
- Tradeoff: inventories must be updated when technical surfaces are added,
  moved, or retired.
- Follow-up: split `scripts/validate_stack.py` by coherent owner surfaces only
  after the relevant inventory and topology tests name the new module.

## Source surfaces

- `docs/validation/`
- `docs/testing/`
- `scripts/validation_lanes.py`
- `scripts/ci_gate.py`
- `scripts/release_check.py`
- `.github/workflows/validate-stack.yml`
- `tests/test_validation_command_authority.py`
- `tests/test_validation_topology.py`
- `tests/test_script_topology.py`
- `tests/test_test_topology.py`

## Follow-up route

Use `scripts/validate_stack.py` as the transitional repo-wide validator until a
bounded owner surface is ready to move into `scripts/validators/`.
