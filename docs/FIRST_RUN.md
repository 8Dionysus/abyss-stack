# FIRST RUN

This guide is the shortest careful path from a source checkout to a running local profile.

## Assumptions

- you are operating in the Fedora-first runtime model
- `podman` is available
- `rsync` is available
- the runtime root should be `/srv/abyss-stack`

If you are starting from Windows, read [WINDOWS_SETUP](WINDOWS_SETUP.md) and use `pwsh -File scripts/aoa.ps1 ...` as the host entrypoint.

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

From a Windows host, the equivalent careful route is:

```powershell
pwsh -File scripts/aoa.ps1 host-doctor
pwsh -File scripts/aoa.ps1 doctor --preset agent-full
pwsh -File scripts/aoa.ps1 first-run --strict
```

## Then do the one thing it cannot do for you

Create the real secret-bearing files described in:
- [SECRETS_BOOTSTRAP](SECRETS_BOOTSTRAP.md)

If the agent API layer is part of the selected profile or preset, verify that `Configs/agent-api/return-policy.yaml` was bootstrapped before launch.

Then validate the fully bootstrapped layout:

```bash
scripts/aoa-check-layout --strict
```

## Optional but recommended: capture host facts

Once the runtime roots exist, record both the public-safe and local-private host posture:

```bash
scripts/aoa-host-facts --mode public --write /tmp/reference-host.public.review.json
scripts/aoa-host-facts --mode private --write "${AOA_STACK_ROOT}/Logs/host-facts/latest.private.json"
```

Review the public artifact before commit.
Do not commit the private artifact.
Keep `docs/reference-platform/reference-host.public.json` reserved for the reviewed canonical Linux reference host snapshot.

## Inspect the profile before launch

```bash
scripts/aoa-profile-modules --profile core
scripts/aoa-profile-endpoints --profile core
```

For absolute module paths:

```bash
scripts/aoa-profile-modules --profile core --paths
```

## Deeper runtime truth before launch

After secrets exist, inspect what Compose actually sees:

```bash
scripts/aoa-render-services --profile core
scripts/aoa-render-config --profile core --write /tmp/abyss-core.rendered.yml
```

Treat the rendered config as potentially secret-bearing.

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
scripts/aoa-render-services --profile agentic
scripts/aoa-up --profile agentic
```

### Intel-aware runtime

This adds OVMS plus the Intel overlay module for the agent API:

```bash
scripts/aoa-profile-modules --profile intel --paths
scripts/aoa-profile-endpoints --profile intel
scripts/aoa-render-services --profile intel
scripts/aoa-up --profile intel
```

## Use a preset instead of spelling the whole composition

```bash
scripts/aoa-preset-profiles --preset agent-full --paths
scripts/aoa-profile-endpoints --preset agent-full
scripts/aoa-render-services --preset agent-full
scripts/aoa-up --preset agent-full
scripts/aoa-smoke --with-internal --preset agent-full
```

## Compose optional layers manually

### Agent runtime plus tools

```bash
scripts/aoa-profile-modules --profile agentic --profile tools --paths
scripts/aoa-profile-endpoints --profile agentic --profile tools
scripts/aoa-render-services --profile agentic --profile tools
scripts/aoa-up --profile agentic --profile tools
scripts/aoa-smoke --with-internal --profile agentic --profile tools
```

### Agent runtime plus tools plus observability

```bash
scripts/aoa-profile-modules --profile agentic,tools,observability --paths
scripts/aoa-profile-endpoints --profile agentic,tools,observability
scripts/aoa-render-services --profile agentic,tools,observability
scripts/aoa-up --profile agentic,tools,observability
scripts/aoa-smoke --with-internal --profile agentic,tools,observability
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
- [REFERENCE_PLATFORM_SPEC](REFERENCE_PLATFORM_SPEC.md)
- [PRESETS](PRESETS.md)
- [PROFILE_RECIPES](PROFILE_RECIPES.md)
- [RENDER_TRUTH](RENDER_TRUTH.md)
- [INTERNAL_PROBES](INTERNAL_PROBES.md)
