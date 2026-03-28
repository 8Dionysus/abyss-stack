# RECURRENCE RUNTIME POLICY

## Purpose

This document defines how the AoA `Recurrence Principle` lands in `abyss-stack`.

At this layer, recurrence becomes a runtime-facing discipline.
`return` remains the concrete recovery move inside that discipline.

`abyss-stack` should not redefine agent meaning, playbook meaning, routing truth, or memory canon.
It should define how the running body detects drift, rebuilds bounded context, records return events, and re-enters safely from the last valid anchor.

## Core rule

When the running route loses its active axis, anchor integrity, verification posture, or bounded context shape, the runtime wrapper should return to the last valid anchor instead of continuing by inertia.

Return is not:

- a blind retry
- permission to widen raw context until something works
- proof that the route was semantically correct
- ownership transfer of routing, memo, playbook, or agent doctrine into this repository

Return means:

1. detect runtime-visible drift
2. resolve the last valid anchor from public upstream surfaces
3. rebuild context in a bounded class-aware way
4. re-enter through an explicit runtime mode
5. stop honestly if anchor-based re-entry is no longer possible

## Why this repository is the right home

`abyss-stack` already owns:

- runtime topology and service modules
- the gateway and agent API layer
- deployment and lifecycle posture
- class-based context budgeting
- infra-facing model profile posture
- public-safe runtime config templates
- runbook and render-truth practices

That makes it the correct layer for executable return policy.

## What this repository may consume

The runtime wrapper may consume public surfaces from neighboring AoA repositories, such as:

- a `transition_decision` that says `return`
- an `anchor_artifact` name from the agent layer
- a checkpoint or bounded recall handle selected upstream
- a scenario hint that narrows re-entry posture
- a playbook advisory card that narrows recall defaults and fallback posture
- a memo recall contract that names inspect, capsule, and expand surfaces without moving memo ownership here

But `abyss-stack` must consume those surfaces without re-owning their authored meaning.

## Runtime-visible drift

At this layer, a return should be available when one or more of the following are true:

- the active route cannot be re-expressed in the stable `core` bucket
- the current response path lost the named anchor it was supposed to work from
- the route widened raw `long` context instead of selecting bounded `memory_access`
- verification posture was expected but the route is trying to continue without it
- repeated stall suggests the route is replaying motion without restoring axis
- a checkpoint-aware route can no longer name the checkpoint it is supposed to relaunch from
- no bounded re-entry can be formed without full-archive loading

These are runtime-facing triggers.
They do not replace the richer authored reasons named upstream.

## Canonical rebuild ladder

The first useful return ladder in `abyss-stack` should be:

1. refresh `core`
2. reset `short` to the active anchor and immediate re-entry note
3. drop raw `long` unless a bounded re-entry slice is explicitly justified
4. load `memory_access` selectively, preferring checkpoint packs before broader recall
5. re-enter through an explicit mode
6. `safe_stop` if no valid anchor remains

In compact form:

```text
core -> anchor-short -> selective-memory_access -> bounded-long-if-needed -> re-enter or safe_stop
```

## Context rebuild rule

The return wrapper should preserve the four existing budget buckets:

- `core`
- `short`
- `long`
- `memory_access`

Return changes how they are rebuilt:

### `core`

Keep this stable and always present.
It should include the route goal, safety and boundary constraints, current runtime selection, and the active role or tier posture as supplied by public upstream surfaces.

### `short`

Replace drifted working state with:

- the active anchor
- the re-entry note
- the smallest local verification or tool evidence still relevant

### `long`

Do not keep raw history by default.
On return, `long` should usually be emptied or compressed, then rebuilt only if the re-entry mode explicitly needs a bounded slice.

### `memory_access`

Prefer:

1. checkpoint pack
2. selected prior decision or verification surfaces
3. selected archive recall only if profile posture allows it

When the live runtime does consume memo recall, the first bounded posture should remain:

```text
inspect -> capsule -> expand
```

Use the capsule step only when the upstream contract publishes it, and keep full expansion as an explicit choice rather than a hidden default.

The wrapper should grow `memory_access` before growing raw `long`.

## Re-entry modes

The runtime layer should keep a small explicit set of re-entry modes:

- `same_phase`
- `previous_phase`
- `router_reentry`
- `checkpoint_relaunch`
- `safe_stop`

Not every route should allow every mode.
The policy should keep the allowed set explicit.

## Profile-class return posture

`abyss-stack` already thinks in class-based model profiles.
Return should therefore stay class-shaped rather than vendor-shaped.

### `spark`

Use the thinnest return posture:

- `core` stays tiny
- `short` becomes anchor-only
- `long` is usually dropped
- `memory_access` should stay highly selective
- return loops should be minimal

### `workhorse`

Use as the default operational return posture:

- stable `core`
- anchor plus local re-entry state in `short`
- selective checkpoint-first `memory_access`
- bounded `long` only if a second slice is justified

### `deep`

Allow richer return support without archive sprawl:

- stable `core`
- bounded but stronger `memory_access`
- optional deeper contradiction or synthesis re-entry
- still no full archive by default

### `archive`

Use summary-first recovery:

- preserve `core`
- rebuild from summary surfaces
- prefer distillation or writeback preparation
- do not turn archive posture into generic free-form continuation

## Logging and inspection

Return should be observable.

A minimal first pass should emit a machine-readable `runtime_return_event` to the runtime logs and preserve references to:

- the runtime selection
- the policy file in effect
- the anchor used
- the rebuild posture
- the re-entry outcome

Recommended log root:

```text
${AOA_STACK_ROOT}/Logs/returns/
```

This keeps return legible in incidents and benchmarks without confusing runtime evidence with authored truth.

## Public-safe config contract

The first implementation pass should keep a public-safe policy file under:

```text
${AOA_STACK_ROOT}/Configs/agent-api/return-policy.yaml
```

That path is a runtime config contract, not secret material.
A bootstrapped template should therefore live under `config-templates/Configs/agent-api/return-policy.yaml`.

## Compose and service stance

The narrowest implementation path is to let the agent-facing runtime service consume the return policy file and write return events to the runtime logs.

For the current stack shape, that most naturally lands in the `41-agent-api.yml` surface.
If the service name changes later, the file contract may stay stable while the consumer changes.
`route-api` remains the advisory facade in this arrangement; it names playbook and memo surfaces, while `langchain-api` is the first live runtime consumer of those surfaces through `POST /run/federated`.

## Render-truth and runbook stance

Return should remain visible in the same operational culture already used elsewhere in the stack:

- render-truth should reveal the mounted policy file and return-log path
- first-run and deployment docs should mention the bootstrapped policy file
- the runbook should tell operators where return events live
- layout checks should verify the runtime policy file when the agent API surface is selected

## Boundaries to preserve

Do not let this landing turn `abyss-stack` into a meaning repository.

This package does not make `abyss-stack` own:

- route semantics as doctrine
- memo truth or archival truth
- agent role meaning
- playbook scenario meaning
- proof that a returned route was correct

It only makes `abyss-stack` own the runtime discipline of anchor-based re-entry.

## Smallest useful landing

The smallest real landing is:

1. add `docs/RECURRENCE_RUNTIME_POLICY.md`
2. add a public-safe return policy template under `config-templates/Configs/agent-api/`
3. mount that file into the agent-facing runtime service
4. write `runtime_return_event` artifacts under `Logs/returns/`
5. mention the contract in context budget, model profiles, deployment, first-run, render-truth, and runbook docs

That is enough to make recurrence runtime-ready without turning the substrate into an epistemic monolith.
