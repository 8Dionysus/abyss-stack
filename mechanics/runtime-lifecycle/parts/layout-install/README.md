# Layout Install

Routes `scripts/aoa-install-layout`, `scripts/aoa-check-layout`,
`mechanics/runtime-lifecycle/parts/layout-install/aoa_install_layout.sh`,
`mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh`,
`docs/PATHS.md`, and `docs/STORAGE_LAYOUT.md`.

Layout install prepares runtime directories; it does not place live state in
the source checkout.

Federation layout checks use clean local labels while still checking upstream
compatibility filenames that sibling mirrors currently publish. Those upstream
filenames are documented in
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.
