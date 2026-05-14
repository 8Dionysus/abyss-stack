# GitHub Homepage README Selection

Status: accepted
Date: 2026-05-14

## Context

GitHub selected `.github/README.md` as the repository homepage README even
though the root `README.md` existed and remained the intended source-checkout
front door. That made the public repository look like the `.github/` district
instead of `abyss-stack`.

## Options considered

1. Keep `.github/README.md` and rely on GitHub eventually preferring root
   `README.md`.
2. Rename the `.github/` human map to a non-README surface and make the
   validator block `.github/README.md` from returning.

## Decision

Keep the root `README.md` as the only homepage README. The `.github/` district
uses `.github/GITHUB_SURFACE.md` as its short human map, and
`scripts/validate_stack.py` treats `.github/README.md` as a residual topology
path that must not return.

## Rationale

The root README is the public source-checkout front door. A hidden platform
district map must not compete with it, even when the hidden district has useful
local guidance. Naming the `.github/` map explicitly keeps the district
discoverable through root routes and local `AGENTS.md` without depending on
GitHub README-selection behavior.

## Consequences

- GitHub should render the root `README.md` on the repository homepage.
- `.github/` still has a short human map, but it is no longer a directory
  README.
- Future platform edits must not recreate `.github/README.md`.

## Source surfaces

- `README.md`
- `.github/GITHUB_SURFACE.md`
- `.github/AGENTS.md`
- `scripts/validate_stack.py`

## Follow-up route

Use `.github/AGENTS.md` and `.github/GITHUB_SURFACE.md` for GitHub-native
surface edits. If GitHub README-selection behavior changes again, update this
decision and the validator together.
