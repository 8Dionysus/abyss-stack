# RENDER TRUTH

`abyss-stack` has several layers of understanding:

- docs and profile descriptions tell you the intended shape
- profile/module introspection tells you the declared shape
- internal probes and smoke tell you what appears healthy after startup
- rendered compose output tells you the **actual composed runtime truth** that Compose sees before launch

This document is about that last layer.

It is not the same thing as autonomy readiness.
Compose truth tells you what should run.
`scripts/aoa-status --autonomy` tells you whether the promoted `llama.cpp + LangGraph + route-api` control loop is coherent on the deployed path.

## Why this matters

Once profiles can be composed, the deepest practical question is no longer just:

**which modules did I declare?**

It becomes:

**what is the final config and final service set after Compose merges everything?**

That is the runtime truth layer.

## Tools

### `aoa-render-services`

Lists the effective service names from the composed runtime view.

Examples:

```bash
scripts/aoa-render-services --profile substrate
scripts/aoa-render-services --profile substrate --profile local-worker
scripts/aoa-render-services --profile fallback-gateway
scripts/aoa-render-services --profile substrate --profile intel-worker
scripts/aoa-render-services --profile substrate,local-worker,tools,observability
```

### `aoa-render-config`

Renders the composed config that Compose sees.

Examples:

```bash
scripts/aoa-render-config --profile substrate
scripts/aoa-render-config --profile substrate --profile local-worker
scripts/aoa-render-config --profile fallback-gateway
scripts/aoa-render-config --profile substrate --profile intel-worker > /tmp/abyss-intel-worker.rendered.yml
scripts/aoa-render-config --profile substrate,local-worker,tools,observability --write /tmp/abyss-worker-tools-observability.rendered.yml
```

## Important caution

Rendered config can be **secret-bearing**.
Depending on env files and resolved settings, it may expose values that should stay local.

Treat rendered output like sensitive runtime material:
- do not paste it publicly
- do not commit it
- prefer writing it to a local file you control
- prefer inspecting it locally and deleting it when done

## Recommended use order

After secrets exist and layout is valid:

```bash
scripts/aoa-check-layout --strict
scripts/aoa-profile-modules --profile substrate --profile local-worker --profile tools --profile observability --paths
scripts/aoa-profile-endpoints --profile substrate --profile local-worker --profile tools --profile observability
scripts/aoa-render-services --profile substrate --profile local-worker --profile tools --profile observability
scripts/aoa-render-config --profile substrate --profile local-worker --profile tools --profile observability --write /tmp/abyss.rendered.yml
```

Only then move to:

```bash
scripts/aoa-up --profile substrate --profile local-worker --profile tools --profile observability
```

## What render-truth is good for

- verifying that multi-profile composition produced the service set you expected
- seeing whether an overlay actually took effect
- spotting duplicate or surprising service definitions before startup
- understanding the final order of merged modules in practice
- debugging profile-composition confusion without starting containers

When the return wrapper is enabled, rendered output should show the mounted return-policy file and writable return-log path for the agent-facing runtime surface.

## What render-truth is not

It is not a replacement for:
- `aoa-doctor`
- `aoa-check-layout`
- `aoa-smoke`
- `aoa-internal-probes`
- `aoa-status --autonomy`

It complements them.
Render-truth tells you what Compose sees.
The other tools tell you what the environment and running containers are doing.
Use route-api `/surface-status` and `aoa-status --autonomy --json` when you need closure and autonomy posture rather than compose composition.
