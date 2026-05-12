# CONTEXT BUDGET POLICY

## Purpose

This document defines class-based context budgeting for `abyss-stack`.

It is a runtime-facing policy.
It does not replace memo doctrine, playbook doctrine, or agent-tier contracts.

## Core rule

Think in context classes, not marketing maxima.

The stack should preserve four budget buckets:

- `core`
- `short`
- `long`
- `memory_access`

## Budget buckets

### `core`

Keep always-small, always-important context here:

- constitutional rules
- route goal
- current role or tier posture
- safety and boundary constraints

This bucket should stay stable even when larger context is unavailable.

### `short`

Use for:

- active step state
- immediate local plan
- current tool outputs
- current verification notes

This is the default working window.

### `long`

Use for:

- bounded multi-step history
- larger source extracts
- current research or synthesis span

This bucket should stay selective.
It is not permission to load everything.

### `memory_access`

Use for:

- selected memo surfaces
- selected prior checkpoints
- selected archival context

This bucket should remain retrieval-shaped and filtered.

## Practical posture by profile class

### `spark`

- very small `core`
- small `short`
- little or no `long`
- highly selective `memory_access`

### `workhorse`

- stable `core`
- moderate `short`
- bounded `long`
- selective `memory_access`

### `deep`

- stable `core`
- moderate `short`
- larger but still bounded `long`
- richer `memory_access`, never full-archive by default

### `archive`

- stable `core`
- moderate `short`
- summary-first `long`
- broader `memory_access` for distillation, not for generic sprawl

## Operational rules

- grow `memory_access` before growing raw `long` context blindly
- compress before escalating hardware assumptions
- do not grant full archive access by default to every route
- keep checkpoint packs and memory candidates smaller than raw history whenever possible

## Return rebuild rule

When a route returns, keep `core` stable, reset `short` to the active anchor and re-entry note, prefer checkpoint-first `memory_access`, and rebuild `long` only if a bounded re-entry slice is explicitly justified.
Do not respond to drift by loading full raw history.

## Boundaries to preserve

- context budget is not proof of capability
- a larger window does not replace memory policy
- `abyss-stack` should not decide canon or truth
- profile and budget policy should remain class-based and hardware-portable
