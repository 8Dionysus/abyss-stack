# RPG Runtime Builders

## Purpose

This note records the minimal builder order for the RPG runtime/body slice.

In this source contract, the builder is filesystem-first and local to `abyss-stack`.
It is not route-api code and it does not widen authority.

## Builder rule

Builders may assemble runtime-owned collections.

Builders may not invent upstream meaning.

## Recommended order

### Phase 1. Refresh build snapshots

Build snapshots combine:
- role and progression refs
- current wrapper/orchestrator posture
- current runtime budgets
- current ability/feat/artifact ids
- capability envelope
- reputation refs if already known

### Phase 2. Refresh quest run results

A run result captures:
- quest ref
- orchestrator posture
- party and build refs
- output summary
- proof refs
- chronicle refs
- penalty previews
- next-hop hints

It must not claim to be the quest itself.

### Phase 3. Refresh reputation ledgers

Reputation comes after evidence and runs.

Ledger refresh may consume:
- run results
- unlock or progression evidence refs
- campaign review refs
- chronicle refs

Keep every slice scoped and cited.

### Phase 4. Refresh frontend bundles

Projection bundles are the last derived layer.

They assemble:
- build cards
- quest board cards
- campaign cards
- timeline entries
- artifact case cards
- reputation panels
- a vocabulary overlay ref

## Validation step

After each refresh pass:

1. validate the collection file against its schema
2. validate each wrapped item against its item schema
3. keep fragment ids stable
4. confirm that source refs are still intact
5. reject outputs that silently overclaim authority

## Storage step

The honest posture in this source contract is filesystem-first:
- source-managed transport under `mechanics/federation-seams/parts/rpg-runtime/generated/`
- live runtime materialization under `Logs/rpg/latest/`
- historical records under `Logs/rpg/records/`

## Anti-patterns

- recomputing unlock proof inside the builder
- awarding progression in the bundle stage
- hiding cause refs behind pretty labels
- turning route-api into the builder itself
- requiring mature mirrors for layers that do not have them yet
- treating ToS language as a replacement for canonical runtime keys

## Final rule

Build upstream, collect downstream, project last.
