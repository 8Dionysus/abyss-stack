# Contributing to abyss-stack

Thank you for contributing.

## What belongs here

Good contributions:
- runtime, deployment, storage, and lifecycle documentation
- compose modules, profiles, presets, and helper scripts
- validation and hardening for stack structure, bootstrap, or operational safety
- public-safe docs that clarify infrastructure boundaries without leaking live details

Bad contributions:
- live secrets, rendered configs, or host-specific runtime files
- widening host exposure from `127.0.0.1` to `0.0.0.0` without explicit operator intent
- changes that blur runtime ownership with `aoa-*` meaning layers
- public docs that include private endpoints, internal-only paths, or secret-bearing output

## Before opening a PR

Please make sure:
- the change is minimal and reversible
- public-safe templates stay separate from live secret-bearing runtime files
- `/srv/AbyssOS/abyss-stack` remains the canonical deployed runtime root unless the change explicitly redesigns it
- host exposure, storage paths, and rollback risks are made explicit when they change
- examples and docs stay sanitized and portable

Run the current repo validation baseline before opening a PR:

```bash
python scripts/validate_stack.py
```

If you touch bootstrap, layout, or lifecycle scripts, also align your validation with the current GitHub workflow in `.github/workflows/validate-stack.yml`.
If you are opening, merging, or retiring topic branches, follow [docs/BRANCH_POLICY.md](docs/BRANCH_POLICY.md).

## Preferred PR scope

Prefer:
- 1 focused infrastructure change per PR
- or 1 focused validation or hardening improvement
- or 1 focused documentation update that clarifies runtime posture
- and 1 short-lived branch per bounded change

## Review criteria

PRs are reviewed for:
- locality and recoverability
- public safety and secret hygiene
- clarity of runtime ownership boundaries
- profile and preset coherence
- validation quality
- branch and merge hygiene

## Security

Do not use public issues or pull requests for leaks, credentials, or infrastructure-sensitive details.
Use the process in `SECURITY.md`.
