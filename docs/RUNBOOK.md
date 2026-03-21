# RUNBOOK

## Quick triage

When something feels wrong, use this order:

1. check profile and module intent
2. check host-readiness and runtime layout
3. check expected profile endpoints and profile composition
4. check internal-only probes when relevant
5. check rendered runtime truth when composition may be the problem
6. check container state
7. check health endpoints
8. check logs
9. decide whether to fix forward or roll back

## Useful commands

```bash
aoa-doctor
aoa-doctor --preset agent-full
aoa-check-layout
aoa-preset-profiles --preset agent-full --paths
aoa-profile-modules --profile core
aoa-profile-endpoints --profile core
aoa-render-services --profile core
aoa-internal-probes --preset agent-full
aoa-status --profile core
aoa-smoke --with-internal --preset agent-full
aoa-logs --profile core
```

For rendered config output:

```bash
aoa-render-config --preset agent-full --write /tmp/abyss.rendered.yml
```

Treat rendered output as potentially secret-bearing.

For combined surfaces:

```bash
aoa-preset-profiles --preset intel-full --paths
aoa-profile-endpoints --preset intel-full
aoa-smoke --with-internal --preset intel-full
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
