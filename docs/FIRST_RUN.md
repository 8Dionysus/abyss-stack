# FIRST RUN

This guide is the shortest careful path from a source checkout to a running local profile.

## Assumptions

- you are operating in the Fedora-first runtime model
- `podman` is available
- `rsync` is available
- the runtime root should be `/srv/abyss-stack`

## Fast path

From the source checkout:

```bash
export AOA_STACK_ROOT=/srv/abyss-stack
export AOA_CONFIGS_ROOT=/srv/abyss-stack/Configs

scripts/aoa-first-run --strict
```

That will:
- create the runtime layout
- sync repo-managed configs and docs
- bootstrap public-safe runtime config templates
- check the layout in strict mode

## Then do the one thing it cannot do for you

Create the real secret-bearing files described in:
- [SECRETS_BOOTSTRAP](SECRETS_BOOTSTRAP.md)

## Inspect the profile before launch

```bash
scripts/aoa-profile-modules --profile core
```

For absolute module paths:

```bash
scripts/aoa-profile-modules --profile core --paths
```

## Bring up the first profile

```bash
scripts/aoa-up --profile core
scripts/aoa-wait --profile core
scripts/aoa-smoke --profile core
```

## Move to richer profiles

### Agent-facing runtime

```bash
scripts/aoa-profile-modules --profile agentic
scripts/aoa-up --profile agentic
```

### Intel-aware runtime

```bash
scripts/aoa-profile-modules --profile intel
scripts/aoa-up --profile intel
```

## Optional helper layers

### Tools

```bash
scripts/aoa-up --profile tools
```

### Observability

```bash
scripts/aoa-up --profile observability
```

## If something feels wrong

Start with:

```bash
scripts/aoa-check-layout
scripts/aoa-status --profile core
scripts/aoa-logs --profile core
```

Then read:
- [RUNBOOK](RUNBOOK.md)
- [DEPLOYMENT](DEPLOYMENT.md)
