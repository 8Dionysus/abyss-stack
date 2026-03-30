# machine-fit

This directory defines the commit-safe contract for `abyss-stack` machine-fit records.

Use it when you need one compact artifact that says:
- what the current host can visibly support
- which runtime selection the stack should currently prefer
- whether the relevant host package set looks fresh in configured repos
- what bounded tuning posture is worth carrying forward on that machine

Surfaces:
- `schema.v1.json` — machine-readable contract
- `machine-fit.public.json.example` — public-safe example shape

Private captures belong under:
- `${AOA_STACK_ROOT}/Logs/machine-fit/`

Do not commit private captures from live machines.
