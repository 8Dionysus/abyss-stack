# Profile Topology Validator Module

- Decision ID: ABYSS-STACK-D-0058
- Status: accepted
- Date: 2026-06-03
- Owner surface: `scripts/validators/profile_topology.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, runtime profile, compose topology
- Stack lanes: source checkout, runtime mechanics, release/tooling
- Mechanic parents: config-projection, runtime-lifecycle, inference-pilots
- Guard families: validation lane, profile topology, composition-first runtime shape, sidecar posture
- Posture: accepted seventeenth validator-module split

## Context

After the mechanics-topology split, `scripts/validate_stack.py` still held the
runtime profile topology contracts. These checks protect composition-first
profiles and presets, module dependency requirements, profile documentation,
GitHub profile rehearsal, the llama.cpp sidecar route, n8n external runner
posture, warmup posture, and active route language that must not depend on
`--profile core`.

This surface is broader than text-file profile parsing. It defines how the
source checkout composes the runtime shape before service-selection policy and
runtime Configs parity can reason about the selected stack.

## Options considered

- Keep profile and preset checks inside `scripts/validate_stack.py`.
- Move only text-file profile and preset parsing, leaving sidecar, n8n, warmup,
  and workflow checks in the root validator.
- Create a focused `scripts/validators/profile_topology.py` module for the full
  composition-first runtime profile contract.

## Decision

Create `scripts/validators/profile_topology.py` and move the implementations
of:

- `validate_profiles`
- `validate_presets`

Move `MODULE_REQUIREMENTS` and related expected profile/preset constants into
the module. Update `compose/AGENTS.md` so module dependency contract changes
route to `scripts/validators/profile_topology.py`.

Keep `scripts/validate_stack.py` as the compatibility entrypoint for existing
callers.

## Rationale

Profile topology is the contract that keeps `abyss-stack` composition-first:
profiles are small composable layers, presets combine them intentionally, and
special routes like the llama.cpp sidecar or n8n runners stay explicit instead
of leaking into normal profiles.

Keeping this surface together avoids splitting the profile text files away
from the docs, workflow rehearsal, sidecar gate, warmup posture, and active
route language that make the profile contract operational.

## Consequences

- Positive: profile topology now has a focused owner module.
- Positive: direct module tests cover current repo validity, module dependency
  drift, sidecar leakage into normal profiles, n8n runner digest pinning,
  active `--profile core` route drift, and preset references.
- Positive: root validator API compatibility remains intact.
- Tradeoff: the module spans compose, docs, workflow, env, and runtime
  lifecycle surfaces because profile topology is an operational composition
  contract, not just a directory of profile files.

## Source surfaces

- `scripts/validators/profile_topology.py`
- `scripts/validate_stack.py`
- `compose/AGENTS.md`
- `compose/profiles/`
- `compose/presets/`
- `compose/modules/`
- `.github/workflows/validate-stack.yml`
- `scripts/aoa-lib.sh`
- `systemd/user/podman-compose-abyss.service`
- `env/stack.env.example`
- `docs/runtime/SERVICE_CATALOG.md`
- `docs/install/DEPLOYMENT.md`
- `mechanics/runtime-lifecycle/parts/start-stop/`
- `tests/test_profile_topology_validator_module.py`

## Follow-up route

Candidate next splits are root README/runtime path guards or inference pilot
compatibility route guards.
