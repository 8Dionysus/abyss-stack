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
7. `docs/PATHS.md`
8. `docs/STORAGE_LAYOUT.md`
9. `docs/DEPLOYMENT.md`
10. `docs/LIFECYCLE.md`
11. `docs/RUNBOOK.md`
12. `docs/SECURITY.md`
13. `docs/MIGRATION_FROM_OLD.md`
