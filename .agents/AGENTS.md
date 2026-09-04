# AGENTS.md

Local guidance for `.agents/` in `abyss-stack`. Read the root `AGENTS.md`
first.

## Scope

This directory owns transitional repo-local agent projections
that need to ship with the `abyss-stack` source checkout.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; `.agents/README.md` is the semantic route when needed, and entering this subtree does not require an unconditional inventory.

## Directory Contract

- Keep canonical skill law in the owning skill repository.
- Keep stack-owned canonical packages under `skills/`, not in this projection.
- Keep local overlays thin, portable, and explicit about the canonical upstream.
- Route bounded edits through the nearest source-owner card; do not create a
  model-branded lane just to duplicate that card's scope and validation.
- Do not commit private agent state, session transcripts, cache payloads, or
  generated runtime captures here.
- Route local overlay references to current package-local mechanics paths.

## Verify

Validation is on-demand: use [VALIDATION.md](../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
