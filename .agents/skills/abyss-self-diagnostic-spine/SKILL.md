---
name: abyss-self-diagnostic-spine
description: Apply the aoa-session-self-diagnose workflow inside abyss-stack using repo-relative runtime evidence, bounded diagnostic-session artifacts, last-good comparison posture, and honest owner-aware handoff. Use when the base diagnosis workflow is correct but abyss-stack needs a thin runtime-owned diagnostic read model before any repair claim becomes honest. Do not use for silent repair, when no concrete target path exists, or when the base skill is sufficient without local adaptation.
license: Apache-2.0
metadata:
  aoa_scope: project
  aoa_status: overlay
  aoa_invocation_mode: explicit-preferred
  aoa_canonical_skill_repo: 8Dionysus/aoa-skills
  aoa_canonical_skill_path: skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md
---

# abyss-self-diagnostic-spine

## Purpose

This is the repo-local install surface for `abyss-stack`.

Use the canonical skill in `aoa-skills` as the source of truth, then adapt it
through the local runtime contracts and docs that live in this repository.

Canonical source:
- `repo:8Dionysus/aoa-skills skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md`

## Local overlay notes

In `abyss-stack`, the diagnostic spine stays:
- runtime-owned
- read-only
- citation-friendly
- separate from mutation authority

Primary local surfaces:
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`
- `scripts/aoa-diagnose`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`
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
