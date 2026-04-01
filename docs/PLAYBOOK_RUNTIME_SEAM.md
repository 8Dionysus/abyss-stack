# PLAYBOOK RUNTIME SEAM

This document defines the advisory-only `aoa-playbooks` landing inside `abyss-stack`.

It is intentionally narrow:
- mirror only public-safe derived `aoa-playbooks` surfaces
- expose them through `/playbooks/*` on the existing localhost-only `route-api`
- do not mirror authored `playbooks/*/PLAYBOOK.md` bundles
- do not add a runtime execution engine, hidden orchestration, or automatic subagent spawning

## What is mirrored from `aoa-playbooks`

The deployed runtime may carry a public-safe mirror under:

- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks`

That mirror is created with:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
```

The current allowlist includes:
- selected docs such as `PLAYBOOK_EXECUTION_SEAM.md` and `PLAYBOOK_LIFECYCLE.md`
- generated registry, activation, federation, review-status, handoff, failure, subagent-recipe, automation-seed, and composition surfaces
- public-safe schemas for the mirrored registry and activation/federation surfaces
- a public-safe schema for the mirrored review-status surface
- public-safe example activation payloads

Authored `playbooks/*/PLAYBOOK.md` bundles are intentionally not mirrored in this phase.
The runtime reads only derived public-safe surfaces, not the authored playbook canon.

## What `/playbooks/*` exposes

The localhost-only `route-api` remains the single federation facade on `127.0.0.1:5402`.

Phase 5 adds a bounded `/playbooks/*` namespace:

Raw read surfaces:
- `GET /playbooks/registry`
- `GET /playbooks/activation`
- `GET /playbooks/federation`
- `GET /playbooks/handoffs`
- `GET /playbooks/failures`
- `GET /playbooks/subagent-recipes`
- `GET /playbooks/automation-seeds`
- `GET /playbooks/composition-manifest`

Structured advisory read surfaces:
- `POST /playbooks/inspect`
- `POST /playbooks/select`
- `POST /playbooks/failure`
- `POST /playbooks/subagent-recipe`
- `POST /playbooks/automation-seed`

`POST /playbooks/inspect` now returns the same compact playbook card as before, plus:

- an optional `review_status` object when the mirrored review-status surface contains a gate-owned entry for that playbook
- an optional `review_packet_contract` object when the mirrored review-packet contract surface contains a derived review-packet entry for that playbook

Both objects are derived from `aoa-playbooks` source-owned review material; neither becomes a second authored truth surface inside the runtime.

These endpoints:
- read only runtime-local mirrored data
- do not execute playbooks
- do not spawn subagents
- do not call sibling repos directly
- do not change `langchain-api`
- remain advisory-only

## Governed execution overlay

The first governed mutation lane does not change this seam into a playbook engine.

- `scripts/aoa-governed-run` resolves playbook cards through `POST /playbooks/inspect` or `POST /playbooks/select`
- runtime permission semantics still live in `abyss-stack`
- file scope, repo scope, break-glass allowance, and acceptance commands come from `${AOA_STACK_ROOT}/Configs/agent-api/governed-execution-policy.yaml`
- trust state, task class, and promotion rubric also live in the runtime policy layer rather than in `aoa-playbooks`
- `aoa-playbooks` still owns playbook meaning; `abyss-stack` only owns the runtime permission overlay

This keeps `/playbooks/*` advisory even when the governed lane uses those surfaces as input.
The governed lane may use `review_packet_contract` only to materialize runtime-owned candidate packets for later human review; it must not mutate `aoa-playbooks` directly.

## What this phase does not do

This landing does not:
- mirror authored `PLAYBOOK.md` bundles
- add a playbook execution engine
- emit execution packets
- trigger automation seeds
- auto-spawn helper agents
- add a new export seam or a new host port

`aoa-playbooks` remains the authority for playbook meaning.
`abyss-stack` only owns the runtime-local advisory mirror and the `/playbooks/*` inspection seam.

## Operational usage

To refresh the public-safe playbook mirror:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
```

To inspect the advisory seam after the `federation` profile is up:

```bash
curl http://127.0.0.1:5402/playbooks/activation
curl http://127.0.0.1:5402/playbooks/federation
curl -X POST http://127.0.0.1:5402/playbooks/inspect \
  -H 'content-type: application/json' \
  -d '{"playbook_id":"AOA-P-0011"}'
```

## One-line rule

`abyss-stack` may mirror `aoa-playbooks` and expose advisory `/playbooks/*` surfaces, but it must not silently become the playbook engine or the playbook authority layer.
