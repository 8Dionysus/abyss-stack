# DOCTOR

`aoa-doctor` is the host-readiness and runtime-readiness probe for `abyss-stack`.

It is meant to answer a simple question before you burn time on startup errors:

**is the current environment shaped enough to run the Fedora-first stack selection I am about to use?**

## What it checks

The current doctor pass looks at things like:
- platform shape such as Linux versus non-Linux
- presence of core commands such as `podman`, `rsync`, and `curl`
- availability of a compose backend
- whether `podman info` works
- whether `systemctl --user` appears usable
- whether `/dev/dri` exists when the selected preset or profile includes Intel-aware inference
- whether the optional vault path appears mounted
- whether the stack root is the canonical `/srv/abyss-stack`
- whether the selected runtime includes internal-only layers that should later be checked with `aoa-smoke --with-internal`
- whether a current machine-fit record is missing for the deployed runtime root
- whether the current host envelope looks noisy for latency-sensitive work

## Preset-aware and profile-aware behavior

`aoa-doctor` can now resolve the same selectors as the runtime wrappers:
- `--preset`
- `--profile`
- repeated flags
- comma-separated forms

That means the doctor output is now contextual.
For example:
- `aoa-doctor --preset agent-full` will not treat missing `/dev/dri` as relevant
- `aoa-doctor --preset intel-full` will warn if `/dev/dri` is missing
- `aoa-doctor --preset agent-full` will remind you that internal-only layers are selected and should be checked after startup

## Relationship to host-facts capture

Use `aoa-doctor` to decide whether a selected runtime is ready to start.

Use `scripts/aoa-host-facts` to capture durable machine-readable host facts.

Use `scripts/aoa-machine-fit` to capture the bounded current-machine runtime posture after host facts exist.

The two surfaces complement each other and should not absorb each other's job.

## Usage

Basic check using the default base profile:

```bash
scripts/aoa-doctor
```

Target a preset:

```bash
scripts/aoa-doctor --preset agent-full
```

Target a specific Intel-aware path:

```bash
scripts/aoa-doctor --preset intel-full
```

Strict check:

```bash
scripts/aoa-doctor --strict --preset intel-full
```

Durable host-facts capture:

```bash
scripts/aoa-host-facts --mode public --write /tmp/reference-host.public.review.json
scripts/aoa-host-facts --mode private --write "${AOA_STACK_ROOT}/Logs/host-facts/latest.private.json"
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
```

Keep `docs/reference-platform/reference-host.public.json` for later canonical-host refreshes, not routine local captures.

## Windows host bridge

If your source checkout lives on Windows and the runtime lives in WSL, start with:

```powershell
pwsh -File scripts/aoa.ps1 host-doctor
pwsh -File scripts/aoa.ps1 doctor --preset agent-full
```

`host-doctor` checks the Windows-side and WSL-side readiness before the Linux doctor is invoked through the bridge.

## Interpreting results

- `ok` means the checked item looks ready
- `warn` means the item is not ideal or is optional in the current context
- `fail` means the current environment is not ready for the expected Fedora-first runtime path

## Important nuance

A warning does not always mean the stack is unusable.
For example:
- `/abyss` not being mounted is a warning, not a hard failure
- `/dev/dri` matters only if the selected preset/profile includes the Intel-aware path
- `systemctl --user` matters for unit-managed lifecycle, not for every manual invocation
- internal-only services are not a doctor failure; they simply mean you should later use `aoa-smoke --with-internal`

## Typical use order

For a generic full bundle:

```bash
scripts/aoa-doctor --preset agent-full
scripts/aoa-first-run --strict
scripts/aoa-check-layout --strict
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
scripts/aoa-smoke --with-internal --preset agent-full
```

For an Intel-aware full bundle:

```bash
scripts/aoa-doctor --preset intel-full
scripts/aoa-first-run --strict
scripts/aoa-check-layout --strict
scripts/aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
scripts/aoa-smoke --with-internal --preset intel-full
```
