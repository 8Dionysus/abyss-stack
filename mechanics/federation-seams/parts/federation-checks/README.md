# Federation Checks

Routes `scripts/aoa-federated-check`,
`mechanics/federation-seams/parts/federation-checks/aoa_federated_check.py`,
the advisory runtime inspection path, and the federation check tests in this
part.

Checks stay read-only and bounded to runtime consumption of owner surfaces.

`docs/UPSTREAM_COMPATIBILITY.md` is the single active bridge for upstream names
that still appear at the route-api or mirror boundary. Active detailed
accounting is `docs/UPSTREAM_COMPATIBILITY_DETAIL.md`; the archived copy stays
in `legacy/upstream-compatibility/INDEX.md`. The runtime data file is
`config-templates/Configs/federation/upstream-compatibility-bridge.json`.
Active local docs should use clean runtime names and route old names through the
bridge only.
