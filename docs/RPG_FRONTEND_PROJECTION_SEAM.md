# RPG Frontend Projection Seam

## Purpose

This note defines how future frontend readers should consume the AoA RPG contour from `abyss-stack`.

The frontend reads one bounded bundle shape rather than scraping many repositories ad hoc.

## Core rule

The frontend reads derived bundles.

It does not become a new authority surface.

## Bundle shape

A good first bundle contains:

- `agent_sheet_cards`
- `quest_board_cards`
- `campaign_lane_cards`
- `progression_timeline_entries`
- `artifact_case_cards`
- `reputation_panels`

The bundle must also preserve:
- a `vocabulary_overlay_ref`
- collection refs for builds, ledgers, and runs
- source refs for quest and campaign surfaces

## Vocabulary posture

The UI may theme labels through the dual-vocabulary overlay.

It must still preserve canonical keys in data or view-model form.

## Public-safe default

Frontend bundles should be public-safe by default.

If a UI needs stronger internal detail later, that should be a different reviewed surface, not a silent widening of the public bundle.

## Action posture

Bundle cards may show actions such as:
- inspect
- expand
- handoff
- verify
- reanchor

The visual affordance is not authority.
Action execution still belongs to owner repos, orchestrators, or reviewed runtime commands.

## Reputation posture

Reputation panels remain:
- slice-based
- cited
- scoped
- capable of negative motion

Do not flatten them into a single prestige meter.

## Final rule

Let the UI sing.

Keep the source refs audible.
