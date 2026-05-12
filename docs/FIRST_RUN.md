# FIRST RUN

This guide is the shortest careful path from a source checkout to a running local profile.

## Assumptions

- you are operating in the Fedora-first runtime model
- `podman` is available
- `rsync` is available
- the runtime root should be `/srv/AbyssOS/abyss-stack`

If you are starting from Windows, read [WINDOWS_SETUP](WINDOWS_SETUP.md) and use `pwsh -File scripts/aoa.ps1 ...` as the host entrypoint.

## Fast path

From the source checkout:

```bash
export AOA_STACK_ROOT=/srv/AbyssOS/abyss-stack
export AOA_CONFIGS_ROOT=/srv/AbyssOS/abyss-stack/Configs

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

## Optional but recommended: capture host facts and machine fit

Once the runtime roots exist, record both the public-safe and local-private host posture, then capture the bounded current-machine fit:

```bash
scripts/aoa-host-facts --mode public --write /tmp/reference-host.public.review.json
scripts/aoa-host-facts --mode private --write "${AOA_STACK_ROOT}/Logs/host-facts/latest.private.json"
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

Review the public artifact before commit.
Do not commit the private artifact.
Only refresh `mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json` when you are intentionally updating the reviewed canonical Linux reference host snapshot.
Refresh the private machine-fit record when kernel, firmware, container runtime, or validated local tuning changes.

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

This is the generic local agent path and defaults to the canonical `llama.cpp` worker path. Embeddings stay disabled unless an explicit backend overlay is added:

```bash
scripts/aoa-profile-modules --profile agentic --paths
scripts/aoa-profile-endpoints --profile agentic
scripts/aoa-render-services --profile agentic
scripts/aoa-up --profile agentic
scripts/aoa-smoke --profile agentic
scripts/aoa-qwen-check --case exact-reply
```

### Intel-aware runtime

This adds OVMS plus the Intel overlay module for the agent API.
In the current reviewed posture, OVMS is used for the explicit embeddings lane while text stays on canonical `llama.cpp`.
Broader Intel-serving experiments should stay in benchmark, machine-fit, or rollout lanes until separately reviewed:

```bash
scripts/aoa-profile-modules --profile intel --paths
scripts/aoa-profile-endpoints --profile intel
scripts/aoa-render-services --profile intel
scripts/aoa-up --profile intel
scripts/aoa-smoke --profile intel
scripts/aoa-qwen-check --case exact-reply
```

## Use a preset instead of spelling the whole composition

```bash
scripts/aoa-preset-profiles --preset agent-full --paths
scripts/aoa-profile-endpoints --preset agent-full
scripts/aoa-render-services --preset agent-full
scripts/aoa-up --preset agent-full
scripts/aoa-smoke --with-internal --preset agent-full
scripts/aoa-qwen-bench --preset agent-full
```

## Optional supervised local AI qualification

Once the intended Qwen path is healthy, materialize the bounded local pilot and run the runtime wave:

```bash
scripts/aoa-local-ai-trials materialize
scripts/aoa-local-ai-trials run-wave W0
```

That flow keeps machine-readable trial truth under `Logs/local-ai-trials/` and writes Markdown mirrors to `Dionysus/reports/local-ai-trials/`.
Use [LOCAL_AI_TRIALS](LOCAL_AI_TRIALS.md) for the full contract.

## Optional bounded llama.cpp pilot

If you want to re-run the bounded `llama.cpp` pilot surfaces explicitly without changing the canonical runtime shape:

```bash
scripts/aoa-llamacpp-pilot run --preset intel-full
```

That pilot re-verifies the bounded `llama.cpp` launch path, starts the explicit pilot sidecar when needed, exposes `langchain-api-llamacpp` on `127.0.0.1:5403`, and writes comparison artifacts under `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/comparisons/`. If the first locally resolved model candidate is rejected by `llama.cpp` on this machine, the pilot falls back to a locally cached curated `bartowski` candidate when one is already present.
Use the same bounded lane for additive Intel 285H host-profile checks such as Gemma 4, Vulkan-first validation, or KV-cache candidate screening instead of treating those as instant defaults.
Use [LLAMACPP_PILOT](LLAMACPP_PILOT.md) for the full contract.

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
- [MACHINE_FIT_POLICY](MACHINE_FIT_POLICY.md)
- [PRESETS](PRESETS.md)
- [PROFILE_RECIPES](PROFILE_RECIPES.md)
- [RENDER_TRUTH](RENDER_TRUTH.md)
- [INTERNAL_PROBES](INTERNAL_PROBES.md)
