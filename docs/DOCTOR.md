# DOCTOR

`aoa-doctor` is the host-readiness and runtime-readiness probe for `abyss-stack`.

It is meant to answer a simple question before you burn time on startup errors:

**is the current environment shaped enough to run the Fedora-first stack?**

## What it checks

The current doctor pass looks at things like:
- platform shape such as Linux versus non-Linux
- presence of core commands such as `podman`, `rsync`, and `curl`
- availability of a compose backend
- whether `podman info` works
- whether `systemctl --user` appears usable
- whether `/dev/dri` exists for Intel-oriented profiles
- whether the optional vault path appears mounted
- whether the stack root is the canonical `/srv/abyss-stack`

## Usage

Basic check:

```bash
scripts/aoa-doctor
```

Strict check:

```bash
scripts/aoa-doctor --strict
```

## Interpreting results

- `ok` means the checked item looks ready
- `warn` means the item is not ideal or is optional in the current context
- `fail` means the current environment is not ready for the expected Fedora-first runtime path

## Important nuance

A warning does not always mean the stack is unusable.
For example:
- `/abyss` not being mounted is a warning, not a hard failure
- `/dev/dri` missing is mainly relevant for Intel-aware paths
- `systemctl --user` matters for unit-managed lifecycle, not for every manual invocation

## Typical use order

```bash
scripts/aoa-doctor
scripts/aoa-first-run --strict
```

Then create secrets and run:

```bash
scripts/aoa-check-layout --strict
```
