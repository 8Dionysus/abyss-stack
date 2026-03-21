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

scripts/aoa-doctor
scripts/aoa-first-run --strict
```

That will:
- check host and runtime prerequisites
- create the runtime layout
- sync repo-managed configs and docs
- bootstrap public-safe runtime config templates
- check the layout in strict bootstrap mode while still allowing missing secrets on that first pass

## Then do the one thing it cannot do for you

Create the real secret-bearing files described in:
- [SECRETS_BOOTSTRAP](SECRETS_BOOTSTRAP.md)

Then validate the fully bootstrapped layout:

```bash
scripts/aoa-check-layout --strict
```

## Inspect the profile before launch

```bash
scripts/aoa-profile-modules --profile core
scripts/aoa-profile-endpoints --profile core
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

This is the generic local agent path and defaults to Ollama-backed embeddings:

```bash
scripts/aoa-profile-modules --profile agentic --paths
scripts/aoa-profile-endpoints --profile agentic
scripts/aoa-up --profile agentic
```

### Intel-aware runtime

This adds OVMS plus the Intel overlay module for the agent API:

```bash
scripts/aoa-profile-modules --profile intel --paths
scripts/aoa-profile-endpoints --profile intel
scripts/aoa-up --profile intel
```

## Optional helper layers

### Tools

```bash
scripts/aoa-profile-endpoints --profile tools
scripts/aoa-up --profile tools
```

### Observability

```bash
scripts/aoa-profile-endpoints --profile observability
scripts/aoa-up --profile observability
```

## If something feels wrong

Start with:

```bash
scripts/aoa-doctor
scripts/aoa-check-layout
scripts/aoa-status --profile core
scripts/aoa-logs --profile core
```

Then read:
- [RUNBOOK](RUNBOOK.md)
- [DEPLOYMENT](DEPLOYMENT.md)
- [DOCTOR](DOCTOR.md)
- [PROFILE_RECIPES](PROFILE_RECIPES.md)
