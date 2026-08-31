# AGENTS.md

Applies to `mechanics/inference-pilots/`.

This package owns the route shape for bounded local inference pilots,
benchmarks, model profiles, and trial evidence.

Read only the source and owner contract needed for the current touched surface; entering this subtree does not require an unconditional README or documentation inventory.

Stable operator wrappers such as `scripts/aoa-llamacpp-pilot`,
`scripts/aoa-qwen-run`, `scripts/aoa-local-ai-trials`, and
`scripts/aoa-tos-foundation-lab` stay at the root
command surface. Active implementations belong under package parts; preserved
compatibility runners belong under owning active package parts and
should be reached through thin part-local bridges.

Do not promote a model, tuning overlay, or worker path without recorded evidence
and a runtime check.

Validation:

Validation is on-demand: use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

Agon dry-run kernels now route through `mechanics/agon-runtime/`.
Archived pilot surfaces route through `mechanics/inference-pilots/legacy/`
and `PROVENANCE.md`; active wrappers must not execute files from that archive.
