---
name: abyss-self-diagnostic-spine
scope: project
status: overlay
summary: Thin repo-local overlay for the abyss diagnostic spine. Canonical skill law lives in aoa-skills and this file keeps the local surface portable across source checkouts, CI, and deployed mirrors.
invocation_mode: explicit-preferred
canonical_skill:
  repo: 8Dionysus/aoa-skills
  path: skills/abyss-self-diagnostic-spine/SKILL.md
---

# abyss-self-diagnostic-spine

## Purpose

This is the repo-local install surface for `abyss-stack`.

Use the canonical skill in `aoa-skills` as the source of truth, then adapt it
through the local runtime contracts and docs that live in this repository.

Canonical source:
- `/srv/aoa-skills/skills/abyss-self-diagnostic-spine/SKILL.md`

## Local overlay notes

In `abyss-stack`, the diagnostic spine stays:
- runtime-owned
- read-only
- citation-friendly
- separate from mutation authority

Primary local surfaces:
- `mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md`
- `scripts/aoa-diagnose`
- `scripts/_aoa_diagnose.py`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json`

## Local rules

- Do not turn `aoa-doctor` into a post-start diagnosis blob.
- Do not bypass review gates for repair.
- Do not move skill canon into this repository.
- Keep repo-local overlays portable across CI and deployed mirrors.
