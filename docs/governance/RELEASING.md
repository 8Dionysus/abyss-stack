# Releasing `abyss-stack`

`abyss-stack` is released as the runtime, deployment, and service substrate beneath AoA and ToS.

See also:

- [README](../README.md)
- [CHANGELOG](../../CHANGELOG.md)
- [DEPLOYMENT](../install/DEPLOYMENT.md)

## Recommended release flow

1. Keep the release bounded to runtime-owned infrastructure truth.
2. Update `CHANGELOG.md` in the `Summary / Validation / Notes` shape.
3. Run decision review for structural, route-law, validator-authority, or
   public-contract changes; use `docs/decisions/` when durable rationale is
   needed.
4. Run the repo-level verifier:
   - `python scripts/release_check.py`
   - GitHub `Repo Validation` reaches the same release command sequence through
     `python scripts/ci_gate.py --mode release`
   - this uses synthetic Configs parity by default; use
     `python scripts/release_check.py --parity-mode live` only after an
     intentional deployed mirror sync
5. Run federation preflight:
   - `aoa release audit /srv --phase preflight --repo abyss-stack --strict --json`
6. Publish only through `aoa release publish`.

## Branch, review, and landing route

When a change is authorized for repository landing:

1. Start from a clean branch based on current `origin/main`.
2. Commit only the intended diff with a message that names the changed surface.
3. Push the branch and open a pull request with changed surfaces, validation,
   skipped checks, and remaining risk.
4. Wait for GitHub `Repo Validation` to finish. If it fails, fix the branch and
   wait for the new result.
5. Merge through GitHub after green validation. Current repository settings
   reject merge commits; use squash unless settings change. If GitHub reports a
   different allowed method for a future PR, use the allowed method and report
   which method landed.
6. Return to `main`, fast-forward from `origin/main`, and confirm the worktree
   is clean before closeout.

If GitHub status or merge permissions cannot be observed, stop the landing
route and report the exact blocker instead of guessing. This route governs
review and landing only; it does not authorize runtime deployment, host
mutation, secret handling, sibling-repository changes, or live parity.
