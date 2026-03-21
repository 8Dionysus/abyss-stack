# INTERNAL PROBES

`aoa-internal-probes` is the runtime check for services that do not expose host ports.

It exists because some surfaces in `abyss-stack` are intentionally internal-only and should not be verified through the host-facing smoke layer.

## What it currently probes

### Browser-tools layer

For the `tools` profile and any other profile that includes `51-browser-tools.yml`:
- `docs-api` via container health status
- `aoa-browser` via container health status

Both of these services already define healthchecks in the compose module, so the internal probe reads their health state through `podman inspect`.

### Observability layer

For the `observability` profile and any other profile that includes `60-monitoring.yml`:
- `cadvisor` via container running state

`cadvisor` is internal-only in the stack. The current probe checks that the container exists and is running. This is intentionally weaker than a dedicated HTTP health probe, but it is still useful and avoids widening host exposure.

## Usage

Basic usage:

```bash
scripts/aoa-internal-probes --profile tools
```

Strict usage:

```bash
scripts/aoa-internal-probes --strict --profile tools
```

## Combining with smoke

You can keep host-facing and internal-only checks separate, or combine them:

```bash
scripts/aoa-smoke --profile observability
scripts/aoa-internal-probes --profile observability
```

Or:

```bash
scripts/aoa-smoke --with-internal --profile observability
```

For stricter combined checks:

```bash
scripts/aoa-smoke --with-internal-strict --profile tools
```

## Important note

A profile can be perfectly healthy even if it has no internal-only services.
In that case the probe will report that there is nothing internal-only to verify for that profile.
