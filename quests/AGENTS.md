# AGENTS.md

Local guidance for the `quests/` questbook district in `abyss-stack`. Read the
root `AGENTS.md` first.

## Scope

This directory owns public, reviewable `abyss-stack` infrastructure obligations
that should survive the current diff.

`QUESTBOOK.md` is the compact root index. Source quest records live under
lane-first lifecycle directories such as
`quests/<lane>/<state>/ABYSS-STACK-Q-*.yaml`. `quests/schemas/` and
`quests/examples/` hold the questbook source contracts and public-safe catalog
or dispatch examples derived from the source records. `quests/scripts/` owns the
quest route helper and derived example builder.

Historical or mechanic-owned quest stubs belong with the owning mechanic legacy
route, not in this root store.

## Local contract

- Keep quest records public-safe, repo-local, and bounded to `abyss-stack`.
- Do not use quests as a private scratchpad, hidden memory, or second roadmap.
- Do not use quest records to absorb AoA, ToS, playbook, memo, eval, or SDK
  owner truth.
- Keep source records, schemas, examples, `quests/scripts/`, `QUESTBOOK.md`, and
  `scripts/validate_stack.py` aligned in the same change.
- Do not add top-level `quests/ABYSS-STACK-Q-*.yaml` aliases; route directly to
  `quests/<lane>/<state>/`.
- When a quest belongs to a mechanic legacy family, move it into that mechanic's
  `legacy/` route with provenance instead of leaving a loose root alias.

## Validate

Use the narrowest checks that cover the touched quest surface from [VALIDATION.md](../VALIDATION.md).
