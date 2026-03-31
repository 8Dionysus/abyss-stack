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
- do not confuse `~/src/abyss-stack` or `${AOA_SOURCE_ROOT}` with `/srv/abyss-stack`
- do not convert public-safe config templates into committed secret-bearing runtime files
- do not publish rendered config output that may contain secret-bearing values
- do not commit private host-facts captures from live machines
- do not turn `aoa-doctor` into a generic inventory or monitoring program

## Default stance

- prefer minimal reversible changes
- prefer profile-aware module changes over all-stack rewrites
- prefer placeholder or skeletal files over pretending unfinished services are complete
- prefer clarity and explicit boundaries over magical automation
- preserve `/srv/abyss-stack` as the canonical deployed runtime root unless explicitly redesigned
- preserve the split between normative platform docs, public-safe host facts, and private host facts
- treat current-machine fit as a first-class runtime concern before latency-sensitive or accelerator-sensitive work

## Host-facts rule

- `docs/REFERENCE_PLATFORM.md` owns the intended host posture.
- `docs/REFERENCE_PLATFORM_SPEC.md` owns the machine-readable contract and capture destinations.
- `docs/MACHINE_FIT_POLICY.md` owns the current-machine adaptation policy and capture destinations.
- `scripts/aoa-doctor` answers readiness, not durable inventory.
- `scripts/aoa-host-facts` captures durable host facts.
- `scripts/aoa-machine-fit` captures the bounded current-machine runtime posture.
- public-safe artifacts may live under `docs/reference-platform/`
- private captures belong under `${AOA_STACK_ROOT}/Logs/host-facts/`
- private machine-fit captures belong under `${AOA_STACK_ROOT}/Logs/machine-fit/`

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
10. `docs/RUNTIME_BENCH_POLICY.md`
11. `docs/INTERNAL_PROBES.md`
12. `docs/PATHS.md`
13. `docs/WINDOWS_BRIDGE.md`
14. `docs/WINDOWS_SETUP.md`
15. `docs/WINDOWS_PERFORMANCE.md`
16. `docs/STORAGE_LAYOUT.md`
17. `docs/REFERENCE_PLATFORM.md`
18. `docs/REFERENCE_PLATFORM_SPEC.md`
19. `docs/DEPLOYMENT.md`
20. `docs/FIRST_RUN.md`
21. `docs/DOCTOR.md`
22. `docs/SECRETS_BOOTSTRAP.md`
23. `docs/LIFECYCLE.md`
24. `docs/RUNBOOK.md`
25. `docs/SECURITY.md`
26. `docs/MIGRATION_FROM_OLD.md`
