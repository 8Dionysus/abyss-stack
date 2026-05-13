# Federation Checks

Routes `scripts/aoa-federated-check`,
`mechanics/federation-seams/parts/federation-checks/aoa_federated_check.py`,
the advisory runtime inspection path, and the federation check tests in this
part.

Checks stay read-only and bounded to runtime consumption of owner surfaces.

`docs/UPSTREAM_COMPATIBILITY.md` is the allowlist for upstream names that still
appear at the route-api or mirror boundary, such as eval selection IDs and
playbook automation compatibility endpoints. Active local docs should use clean
runtime aliases and route old names through that verdict table.
