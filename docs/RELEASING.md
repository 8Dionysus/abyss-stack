# Releasing `abyss-stack`

`abyss-stack` is released as the runtime, deployment, and service substrate beneath AoA and ToS.

See also:

- [README](../README.md)
- [CHANGELOG](../CHANGELOG.md)
- [DEPLOYMENT](DEPLOYMENT.md)

## Recommended release flow

1. Keep the release bounded to runtime-owned infrastructure truth.
2. Update `CHANGELOG.md` in the `Summary / Validation / Notes` shape.
3. Run the repo-level verifier:
   - `python scripts/release_check.py`
4. Run federation preflight:
   - `aoa release audit /srv --phase preflight --repo abyss-stack --strict --json`
5. Publish only through `aoa release publish`.
