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
