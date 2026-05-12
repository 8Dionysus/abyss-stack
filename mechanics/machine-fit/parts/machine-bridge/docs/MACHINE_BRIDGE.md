# MACHINE BRIDGE

## Purpose

This document defines the stack-side consumer route for `abyss-machine`.

`abyss-machine` owns host control-plane facts, hardware routing, resource gates,
storage policy, process/container evidence, and local chronicle state.
`abyss-stack` consumes those facts so runtime agents and operators can find a
single bridge record from the stack side without scraping host paths directly.

## Contract

- Owner of host truth: `abyss-machine`
- Consumer and runtime adapter: `abyss-stack`
- Stack command: `scripts/aoa-machine-bridge --write-latest`
- Host source command: `abyss-machine stack-bridge export --json`
- Host validation command: `abyss-machine stack-bridge validate --json`
- Stack latest record: `${AOA_STACK_ROOT}/Logs/machine-bridge/latest/latest.private.json`
- Stack history root: `${AOA_STACK_ROOT}/Logs/machine-bridge/records/`
- Stack index: `${AOA_STACK_ROOT}/Logs/machine-bridge/index.json`

The bridge is read-only toward the machine. It does not start services, change
power modes, write host policy, move Podman storage, clean caches, or mutate
process affinity.

## Topology

```text
abyss-machine
  /etc/abyss-machine/bridge.json
  /etc/abyss-machine/stack-bridge.json
  /var/lib/abyss-machine/stack-bridge/latest.json
  /var/lib/abyss-machine/{ai,memory,resource,storage,processes,...}/
        |
        | read-only capture
        v
abyss-stack
  Logs/machine-bridge/
    index.json
    latest/latest.private.json
    records/<bridge-id>/machine-bridge.private.json
  Logs/host-facts/
  Logs/machine-fit/
  Logs/diagnostics/
```

This keeps the map branch-shaped:

- `abyss-machine` remains the machine owner.
- `abyss-stack` owns runtime-local bridge records and stack decisions.
- `aoa-host-facts` captures observed host shape.
- `aoa-machine-fit` records preferred runtime posture.
- `aoa-diagnose` consumes runtime and bridge evidence after services are live.

## Artifact Shape

The runtime artifact uses `artifact_kind=aoa.machine-bridge` and is defined by
`schemas/schema.v1.json` in this part.

It includes:

- contract and dependency direction
- stack log and index routes
- `index.json` with `latest`, `latest_record`, `records_root`, and a compact
  `records[]` list for agent-readable history traversal
- host bridge summary
- indexed host evidence refs grouped by class
- command catalog for future agents
- compact live evidence summaries such as mode, memory, storage, LLM, nervous,
  and rootless Podman container health
- explicit non-claims

Private records may include local paths and process/container names. They must
not be committed. Public records redact local paths and omit raw host payloads.

## Usage

Refresh the local private bridge record:

```bash
scripts/aoa-machine-bridge --write-latest
```

Check that the host bridge is reachable and validates:

```bash
scripts/aoa-machine-bridge --check
```

Capture a public-safe review artifact:

```bash
scripts/aoa-machine-bridge --mode public --write /tmp/machine-bridge.public.review.json
```

Recommended local sequence before heavy local AI, long-running agents, or
runtime diagnosis:

```bash
scripts/aoa-machine-bridge --write-latest
scripts/aoa-host-facts --mode private --write "${AOA_STACK_ROOT}/Logs/host-facts/latest.private.json"
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
scripts/aoa-doctor --preset intel-full
```

## Relationship To Existing Surfaces

`aoa-machine-bridge` does not replace:

- `aoa-host-facts`, which captures host facts in the stack schema
- `aoa-machine-fit`, which records preferred runtime posture
- `aoa-platform-adaptation`, which records a bounded stack-side seam bend
- `aoa-diagnose`, which diagnoses a selected live runtime target
- `abyss-machine`, which remains the host control plane

It is the route index between them.

## Stop Lines

Do not use this bridge to:

- import `abyss-machine` implementation into `abyss-stack`
- modify `/var/lib/abyss-machine`, `/srv/abyss-machine`, or host policy
- treat generated summaries as source truth
- commit private captures from `${AOA_STACK_ROOT}/Logs/machine-bridge/`
- promote a model/runtime lane without separate benchmark and review evidence
