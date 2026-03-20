# CHARTER

`abyss-stack` is the infrastructure substrate repository of the AoA and ToS ecosystem.

Its job is to keep the runtime body explicit, modular, reviewable, and recoverable.

## It owns

- deployment topology
- runtime modules
- local and hybrid service wiring
- storage layout
- secrets boundaries and mount contracts
- lifecycle operations
- runbook and recovery posture
- infrastructure helper services

## It does not own

- ecosystem-level doctrine for AoA as a whole
- authored meaning from `aoa-techniques`, `aoa-skills`, `aoa-evals`, `aoa-routing`, `aoa-memo`, `aoa-agents`, `aoa-playbooks`, or `aoa-kag`
- the primary authored corpus of Tree of Sophia

## Core rule

**This repository owns runtime, not meaning.**

## Design stance

- modular growth over infra monoliths
- localhost-first exposure boundaries
- rootless operation by default
- explicit profiles over hidden coupling
- operational clarity over cleverness
- reversible changes over wide refactors
