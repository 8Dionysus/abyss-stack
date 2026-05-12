# 2026-05-12 Machine Bridge Under Machine Fit

## Status

Accepted.

## Context

`abyss-stack` needs a read-only stack-side route into `abyss-machine` evidence:
host control-plane refs, launch gates, storage and process summaries, and
machine-owned bridge validation.

The repository already has a `machine-fit` mechanic for reference platform
facts, host-facts capture, machine-fit records, platform adaptation, and
machine-owner boundaries. Adding a new root `docs/MACHINE_BRIDGE.md` plus
`docs/machine-bridge/` would make the next machine contract look like another
flat root district even though the owning mechanic is clear.

## Options

1. Keep `MACHINE_BRIDGE.md` and `docs/machine-bridge/` in root `docs/`.
2. Move the entire command and contract under `mechanics/machine-fit/`.
3. Keep the operator command in root `scripts/`, but move the active bridge
   contract, schema, public example, and focused contract test under
   `mechanics/machine-fit/`.

## Decision

Use option 3.

`scripts/aoa-machine-bridge` remains the root operator command because deployed
runtime mirrors and operators expect commands in `scripts/`. The bridge
contract and proof surfaces live under:

- `mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md`
- `mechanics/machine-fit/parts/machine-bridge/`
- `mechanics/machine-fit/parts/machine-bridge/tests/test_machine_bridge_contracts.py`

## Rationale

Machine bridge is active, not legacy, so it should not go under `legacy/`.
It also should not stay as a new root doc island because `machine-fit` already
owns the boundary between stack runtime posture and machine-owned facts.

This keeps the topology convex: root routes point to the package home,
package docs own the bridge contract, and the root script stays as a stable
operator entrypoint.

## Consequences

- Future machine-bridge contract changes start in
  `mechanics/machine-fit/parts/machine-bridge/`.
- `scripts/validate_stack.py` validates the package-local schema and example.
- `abyss-machine` remains the stronger owner of host control-plane truth.
- `abyss-stack` records runtime-local bridge evidence but does not mutate the
  machine, launch policy, storage policy, caches, or process affinity.
