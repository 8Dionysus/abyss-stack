# RUNBOOK

## Quick triage

When something feels wrong, use this order:

1. check profile and module intent
2. check host-readiness and runtime layout
3. check expected profile endpoints and profile composition
4. check container state
5. check health endpoints
6. check logs
7. decide whether to fix forward or roll back

## Useful commands

```bash
aoa-doctor
aoa-check-layout
aoa-profile-modules --profile core
aoa-profile-endpoints --profile core
aoa-status --profile core
aoa-smoke --profile core
aoa-logs --profile core
```

Low-level checks:

```bash
systemctl --user status podman-compose-abyss --no-pager
podman ps -a --no-trunc
ss -lntp
```

## Internal-only services

These should not expose host ports:
- `docs-api`
- `aoa-browser`
- `cadvisor`

If they accidentally appear on host ports, treat that as drift.

## First rollback instinct

If a change widened scope, broke locality, tangled profiles, or mixed Windows host paths with Linux runtime paths, prefer a small rollback over improvising a giant repair.
