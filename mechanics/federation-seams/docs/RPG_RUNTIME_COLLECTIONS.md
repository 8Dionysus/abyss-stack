# RPG Runtime Collections

## Purpose

This note defines the runtime-owned collection layer for the AoA RPG contour inside `abyss-stack`.

It turns the canonical item contracts from the RPG architecture RFC into collection-shaped transport surfaces that services, SDK consumers, and future frontend code can read directly.

## Core rule

`abyss-stack` owns the collections.

It does not own the upstream meanings the collections cite.

## Source-managed transport paths

The source repository keeps public-safe generated transport files under:

```text
mechanics/federation-seams/parts/rpg-runtime/generated/
  agent_build_snapshots.json
  reputation_ledgers.json
  quest_run_results.json
  frontend_projection_bundles.json
```

These files are:
- public-safe by default
- collection-wrapped
- meant for validation, review, SDK loading, and future runtime handoff
- not substitutes for upstream source-owned truth

## Deployed runtime materialization

The live deployed runtime materializes the latest runtime-owned collections under:

```text
${AOA_STACK_ROOT}/Logs/rpg/latest/
  agent_build_snapshots.json
  reputation_ledgers.json
  quest_run_results.json
  frontend_projection_bundles.json
```

Historical records accumulate under:

```text
${AOA_STACK_ROOT}/Logs/rpg/records/
```

The runtime may prefer the live `Logs/rpg/latest/` copies.
Source-managed `mechanics/federation-seams/parts/rpg-runtime/generated/` files remain the public-safe transport and validation shape.

## The four collections

### 1. `agent_build_snapshot_collection_v1`

Runtime-readable build state for agents:
- class reflection
- execution origin
- current reviewed mastery posture
- current loadout refs
- capability envelope
- runtime budgets
- reputation refs

### 2. `reputation_ledger_collection_v1`

Scoped, cited trust slices for:
- agents
- parties
- campaigns
- artifacts when necessary

No universal karma number lives here.

### 3. `quest_run_result_collection_v1`

Bounded run envelopes:
- quest refs
- party and build refs
- orchestrator posture
- outputs, proof refs, chronicle refs
- penalties and next hops
- non-authoritative quest-state hints only

### 4. `frontend_projection_bundle_collection_v1`

Reader-facing bundle cards:
- agent sheets
- quest board cards
- campaign lane cards
- progression timeline entries
- artifact case cards
- reputation panels

## Input posture

Good first-pass inputs:

- `aoa-agents` role and progression surfaces
- `aoa-routing` board or navigation hints
- `aoa-evals` progression or unlock evidence refs
- `aoa-playbooks` campaign or composition refs
- `aoa-memo` chronicle refs
- runtime run envelopes and current tool/wrapper posture

Optional in this pass:
- `aoa-skills` ability refs
- `aoa-techniques` feat refs
- `Agents-of-Abyss` dual-vocabulary overlay ref

Those optional inputs may stay pass-through refs.
They do not require runtime-local mirrors in this source contract.

## Write posture

These collections are runtime-owned read models.

They may:
- aggregate refs
- preserve current runtime posture
- provide frontend-readable bundles
- expose collection-level history in `Logs/rpg/records/`

They must not:
- overwrite source quest state
- rewrite role meaning
- rewrite skill or technique meaning
- compute proof verdicts
- publish back into upstream repos automatically

## Privacy posture

Keep the public-safe default strong.

Do not leak:
- secrets
- private runtime prompts
- raw hidden scratchpad
- operator-only notes that were never intended for public-safe projection

## Final rule

A runtime collection is a read model with memory.

It is not a new canon.
