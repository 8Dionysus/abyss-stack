# ROADMAP

## Current posture

The bootstrap-to-federation landing path is largely complete.
Phases 0 through 6 have already been landed as source and runtime seams:

- modular runtime bootstrap
- service extraction and profile-aware lifecycle wrappers
- Intel-aware and Windows-usable hardening
- `aoa-agents`, `aoa-routing`, `aoa-memo`, `aoa-evals`, `aoa-playbooks`, and `aoa-kag` advisory/read-export landings
- `Tree-of-Sophia` source-owned handoff companion landing

The main remaining work is live runtime-loop consumption, operational cutover choices, and platform hardening rather than another large mirror phase.

## Phase 0: structured bootstrap

- establish repository charter and boundaries
- create modular compose skeleton
- define first runtime profiles
- define env and secrets posture
- write migration notes from `abyss-stack_old`

## Phase 1: service extraction

- reintroduce storage services cleanly
- reintroduce orchestration and local inference
- reintroduce gateway and agent API modules
- reintroduce speech, browser, and monitoring modules

## Phase 2: operational hardening

- add smoke and health routines
- add profile-aware lifecycle wrappers
- add backup and restore helpers
- add validation for compose coherence
- reduce environment-specific assumptions where possible
- enforce the new `/srv/abyss-stack` canonical runtime root
- make the Fedora-first and Windows-usable path model explicit
- make deployment from source checkout to runtime tree explicit and repeatable

## Phase 3: hybrid growth

- clarify local versus hybrid execution paths
- refine Intel and OVMS posture
- define clean bridges to sibling AoA repositories

## Phase 4: mature substrate

- keep the stack legible under growth
- resist monolith relapse
- let new capability arrive as modules and profiles rather than as hidden sprawl

## Phase 5: live runtime consumption

- decide which federation seams remain advisory-only and which become part of the live loop
- introduce bounded recall, playbook, eval, and KAG consumption in explicit steps
- preserve source-owned authority while adding runtime utility

## Phase 6: platform and operations hardening

- keep runtime cleanup repeatable and legible
- validate reboot and cold-start behavior
- tighten runtime-secret hygiene and stateful-data discipline
- keep Windows and Fedora rollout paths aligned with the same operational model
