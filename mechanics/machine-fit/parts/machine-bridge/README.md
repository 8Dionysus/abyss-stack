# machine-bridge

This directory defines the public contract for the stack-side `abyss-machine`
bridge artifact.

## Files

- `schemas/schema.v1.json` - machine-readable contract for `aoa.machine-bridge`
- `examples/machine-bridge.public.json.example` - public-safe example shape
- `aoa_machine_bridge.py` - part-local backend for
  `scripts/aoa-machine-bridge`

## Runtime Capture

Local private captures belong under:

```text
${AOA_STACK_ROOT}/Logs/machine-bridge/
  index.json
  latest/latest.private.json
  records/<bridge-id>/machine-bridge.private.json
```

Do not commit private captures. They may include local paths and
process/container names.
