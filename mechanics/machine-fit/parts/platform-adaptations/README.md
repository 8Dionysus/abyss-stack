# Platform Adaptations

This directory defines the commit-safe contract for `abyss-stack` platform-adaptation records.

Use it when you need one compact artifact that says:
- what platform seam bent
- what runtime adaptation helped
- what should be re-tested when the stack moves to another platform

Surfaces:
- `docs/PLATFORM_ADAPTATION_POLICY.md` - bounded platform-adaptation policy
- `schemas/schema.v1.json` - machine-readable contract
- `examples/platform-adaptation.public.json.example` - public-safe example shape
- `aoa_platform_adaptation.py` - part-local backend for
  `scripts/aoa-platform-adaptation`

Private captures belong under:
- `${AOA_STACK_ROOT}/Logs/platform-adaptations/`

Do not commit private captures from live machines.
