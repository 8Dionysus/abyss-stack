# AGENTS

Rules for coding agents and maintainers working in `abyss-stack`.

## Mission

Move the stack forward without breaking locality, secrecy, recoverability, or the Fedora-first deployment posture.

## Core protocol

Use this order:

`PLAN -> DIFF -> APPLY -> VERIFY -> REPORT`

## Hard no

- do not print or commit real secrets
- do not read or expose secret-bearing files from live hosts
- do not widen host exposure from `127.0.0.1` to `0.0.0.0` without explicit operator intent
- do not perform destructive data actions without an explicit rollback path
- do not silently merge runtime and meaning layers back together
- do not confuse a Windows source checkout path with the Linux runtime root
- do not convert public-safe config templates into committed secret-bearing runtime files
- do not publish rendered config output that may contain secret-bearing values

## Default stance

- prefer minimal reversible changes
- prefer profile-aware module changes over all-stack rewrites
- prefer placeholder or skeletal files over pretending unfinished services are complete
- prefer clarity and explicit boundaries over magical automation
- preserve `/srv/abyss-stack` as the canonical deployed runtime root unless explicitly redesigned

## Repository reading order

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SERVICE_CATALOG.md`
6. `docs/PROFILES.md`
7. `docs/PRESETS.md`
8. `docs/PROFILE_RECIPES.md`
9. `docs/RENDER_TRUTH.md`
10. `docs/INTERNAL_PROBES.md`
11. `docs/PATHS.md`
12. `docs/STORAGE_LAYOUT.md`
13. `docs/DEPLOYMENT.md`
14. `docs/FIRST_RUN.md`
15. `docs/DOCTOR.md`
16. `docs/SECRETS_BOOTSTRAP.md`
17. `docs/LIFECYCLE.md`
18. `docs/RUNBOOK.md`
19. `docs/SECURITY.md`
20. `docs/MIGRATION_FROM_OLD.md`
