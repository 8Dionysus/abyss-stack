# AGENTS.md

Applies to `mechanics/runtime-repair/legacy/`.

This directory preserves the runtime repair archive lineage after the mechanics
topology refactor.

Use `../README.md` and `../PROVENANCE.md` before treating a legacy artifact as
current evidence. Raw docs in `legacy/raw/` are historical source material.
`legacy/artifacts/` is a bridge to the active receipt parts, not an active
contract home.

Do not:

- move `_v1` receipt schemas back into root `schemas/`
- treat a chaos wave note as active recovery law
- claim that a receipt proves repair or root cause
- hand-edit active receipt examples without running the package tests

Validation:

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
