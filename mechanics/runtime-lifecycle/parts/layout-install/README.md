# Layout Install

Routes `scripts/aoa-install-layout`, `scripts/aoa-check-layout`,
`mechanics/runtime-lifecycle/parts/layout-install/aoa_install_layout.sh`,
`mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh`,
`docs/runtime/PATHS.md`, and `docs/runtime/STORAGE_LAYOUT.md`.

Layout install prepares runtime directories; it does not place live state in
the source checkout.

When observability is selected, persistent Prometheus, Alertmanager, Loki,
Tempo, Alloy, and Grafana state lives under `Services/monitoring/`. Those
directories are explicit Podman bind sources so SELinux relabel intent remains
visible in the rendered container mounts.

Federation layout checks use clean local labels while still checking upstream
compatibility filenames that sibling mirrors currently publish. Those upstream
filenames are documented in
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.
