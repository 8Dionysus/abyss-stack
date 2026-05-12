# RPG Runtime Frontend Posture

## Purpose

This note defines the first runtime/frontend contract boundary for the AoA RPG contour inside `abyss-stack`.

The goal is to let runtime services and future frontend surfaces read the federation clearly without becoming a shadow authority layer.

## Core rule

`abyss-stack` owns runtime state and service delivery.

It does not own upstream meaning.

## What belongs here

For this contour, `abyss-stack` is the right home for:
- build snapshots
- runtime resource budgets
- current equipped loadout
- current tool bundles and wrapper posture
- scoped reputation ledgers
- quest run result envelopes
- frontend projection bundles
- later service APIs or caches built from these contracts

## What does not belong here

This repo must not absorb:
- source quest meaning
- role doctrine
- skill canon
- technique canon
- eval verdict doctrine
- memo object canon
- playbook meaning
- routing truth as such

## Required inputs

These runtime contracts are expected to read from upstream surfaces such as:
- role and progression overlays from `aoa-agents`
- ability and feat reflections from `aoa-skills` and `aoa-techniques`
- progression evidence and caution posture from `aoa-evals`
- playbook activation or campaign refs from `aoa-playbooks`
- chronicle refs from `aoa-memo`
- thin quest or entry hints from `aoa-routing`

The runtime may cache or aggregate these refs.

It may not silently replace them.

## First runtime objects

This RFC lands four runtime-facing contracts:

1. `agent_build_snapshot_v1`
2. `reputation_ledger_v1`
3. `quest_run_result_v1`
4. `frontend_projection_bundle_v1`

These are service contracts, not new source doctrines.

## No-hidden-writeback rule

Runtime services may produce:
- source refs
- build snapshots
- UI projections
- progress previews
- reputation previews
- non-authoritative quest-state hints

Runtime services may not directly rewrite:
- source quest state
- source role contracts
- source skill or technique docs
- source eval doctrine
- source memo objects

All stronger writeback must happen through the existing owner surfaces.

## Orchestrator posture

Codex is the primary orchestrator driver at the current stage.

The runtime contracts still remain orchestrator-agnostic:
- always record `orchestrator_kind`
- always record `run_mode`
- always record `wrapper_class`

This keeps the contour open to later local, hybrid, or SDK-driven runners.

## Frontend posture

The frontend should consume one bounded projection bundle rather than scraping every repo ad hoc.

That bundle must:
- preserve source refs
- preserve canonical keys
- allow theming through `dual_vocabulary_overlay_v1`
- stay public-safe by default

The frontend must not become an authority surface.

## Resource posture

Runtime resources are budgets, not metaphysical truth.

They are current operational summaries designed for:
- session readability
- safe gating
- honest replay
- later projection into themed bars or meters

## Reputation posture

Reputation is not a secret reward function.

It is a scoped and cited trust ledger.

Good reputation entries name:
- the trust axis
- the owner scope
- the cause
- the evidence
- the last change
- the current standing

## Artifact posture

Artifacts remain weaker than the existing source-owned contours in this pass.

For now:
- artifact IDs are allowed in runtime build snapshots and projection bundles
- artifact meaning must cite source refs or runtime cause refs
- artifacts do not become a new canon hidden inside `abyss-stack`

## Final rule

`abyss-stack` should feel like the living body of the system.

It must never pretend to be the soul.
