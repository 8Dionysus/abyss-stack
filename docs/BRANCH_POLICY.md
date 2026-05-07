# Branch Policy

`abyss-stack` should stay easy to merge, easy to prune, and easy to reason about from `main`.

## Canonical branch

- `main` is the only long-lived branch.
- `main` should always represent the best known merge of repo-managed stack truth.
- Do not keep parallel long-lived integration branches for runtime, docs, or platform work.

## Topic branches

- Use short-lived topic branches for reviewable work.
- Prefer names that explain one wave only:
  - `codex/<focused-wave>`
  - `docs/<focused-wave>`
  - `ops/<focused-wave>`
- One branch should carry one bounded concern:
  - one federation wave
  - one platform-adaptation layer
  - one runtime hardening pass
  - one docs clarification set

## Commit shape

- Keep commits locally coherent before merge.
- Split unrelated layers when they can stand on their own:
  - docs or policy
  - federation seam
  - runtime performance or lifecycle fix
- Do not mix runtime-only local state with repo-managed source changes in one commit.

## Preferred merge path

1. Start from current `main`.
2. Create one short-lived topic branch.
3. Keep the branch rebased or otherwise current with `main`.
4. Validate before merge:
   - `python scripts/validate_stack.py`
   - any syntax or smoke checks touched by the change
5. Merge the branch into `main` once the branch is internally clean.
6. Push `main`.
7. Delete the topic branch locally and on `origin`.

## Merge rules

- Prefer one clean merge into `main` over stacked half-merged branches.
- If a branch was effectively landed by squash, cherry-pick, or a rewritten equivalent, do not merge it again.
- In that case:
  - confirm the patch is already represented in `main`
  - push `main`
  - delete the stale branch
- Do not leave old `codex/*` or other topic branches on `origin` once their changes are already in `main`.

## Direct commits to `main`

- Direct commits to `main` are acceptable only when the work is already operator-verified and splitting into a separate review branch adds noise rather than safety.
- Even then, keep the commit single-purpose and validation-backed.
- If the worktree contains multiple concerns, split them into separate commits before pushing `main`.

## Runtime-aware hygiene

- `/srv/AbyssOS/abyss-stack` is runtime state, not branch truth.
- `~/src/abyss-stack` or `${AOA_SOURCE_ROOT}` is source truth.
- If a fix is proven first in the live runtime, vendor it back into the source checkout before merge.
- Do not treat runtime drift as implicitly merged work.

## Branch retirement checklist

- `git status` is clean.
- `main` contains the intended patch.
- `origin/main` is updated.
- old topic branches with no remaining unique patch are deleted from `origin`.
- any follow-up work gets a new topic branch rather than reviving an old one.
