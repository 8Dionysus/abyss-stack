# RUNBOOK

## Quick triage

When something feels wrong, use this order:

1. check profile and module intent
2. check container state
3. check health endpoints
4. check logs
5. decide whether to fix forward or roll back

## Useful commands

```bash
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

If a change widened scope, broke locality, or tangled profiles, prefer a small rollback over improvising a giant repair.
