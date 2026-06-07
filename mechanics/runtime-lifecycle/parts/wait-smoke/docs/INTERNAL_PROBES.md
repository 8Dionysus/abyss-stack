# INTERNAL PROBES

`aoa-internal-probes` is the runtime check for services that do not expose host ports.

It exists because some surfaces in `abyss-stack` are intentionally internal-only and should not be verified through the host-facing smoke layer.

## What it currently probes

### Browser-tools layer

For the `tools` profile and any preset or profile-combination that includes `51-browser-tools.yml`:
- `docs-api` via container health status
- `aoa-browser` via container health status

Both of these services already define healthchecks in the compose module, so the internal probe reads their health state through `podman inspect`.

### Observability layer

For the `observability` profile and any preset or profile-combination that includes `60-monitoring.yml`:
- `cadvisor` via container running state
- `loki` via container running state
- `alloy` via container running state

These services are internal-only in the stack. The current probe checks that the
container exists and is running. This is intentionally weaker than a dedicated
HTTP health probe, but it is still useful and avoids widening host exposure.

## Usage

Basic usage against a profile:

```bash
scripts/aoa-internal-probes --profile tools
```

Usage against a preset:

```bash
scripts/aoa-internal-probes --preset agent-full
```

Strict usage:

```bash
scripts/aoa-internal-probes --strict --preset intel-full
```

## Combining with smoke

You can keep host-facing and internal-only checks separate, or combine them.

### Profile form

```bash
scripts/aoa-smoke --profile observability
scripts/aoa-internal-probes --profile observability
```

### Preset form

```bash
scripts/aoa-smoke --preset agent-full
scripts/aoa-internal-probes --preset agent-full
```

Or combine them in one pass:

```bash
scripts/aoa-smoke --with-internal --preset agent-full
```

For stricter combined checks:

```bash
scripts/aoa-smoke --with-internal-strict --preset intel-full
```

## Important note

A preset or profile can be perfectly healthy even if it has no internal-only services.
In that case the probe will report that there is nothing internal-only to verify for that selection.
