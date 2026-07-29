# CHARTER

`abyss-stack` is the infrastructure substrate repository of the AoA and ToS ecosystem.

Its job is to keep the runtime body explicit, modular, reviewable, and recoverable.

## It owns

- deployment topology
- working substrate runtime selection
- runtime modules
- local and hybrid service wiring
- storage layout
- secrets boundaries and mount contracts
- lifecycle operations
- runbook and recovery posture
- infrastructure helper services
- owner skill packages for stack-owned runtime procedures

## It does not own

- ecosystem-level doctrine for AoA as a whole
- shared or sibling-authored meaning from `aoa-techniques`, `aoa-skills`,
  `aoa-evals`, `aoa-sdk` routing, `aoa-memo`, `aoa-agents`,
  `aoa-playbooks`, or `aoa-kag`
- the primary authored corpus of Tree of Sophia

## Core rule

**This repository owns runtime, not meaning.**

## Design stance

- Fedora-first deployment posture
- Windows-usable source and path model
- modular growth over infra monoliths
- localhost-first exposure boundaries
- rootless operation by default
- explicit profiles over hidden coupling
- anchor-based return over drifted continuity when runtime routes lose shape
- operational clarity over cleverness
- reversible changes over wide refactors

`DESIGN.md` owns the system-form description for this stance.
`DESIGN.AGENTS.md` owns the form of agent-facing route guidance.
