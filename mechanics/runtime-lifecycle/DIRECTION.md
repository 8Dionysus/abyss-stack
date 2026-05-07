# Runtime Lifecycle Direction

The current contour is route-first and dry-run-friendly.

Short term:

- keep `aoa-up`, `aoa-down`, `aoa-wait`, `aoa-smoke`, and `aoa-logs` discoverable from `scripts/`
- keep `systemd/user/podman-compose-abyss.service` pointed at deployed `Configs`
- keep docs explicit that source sync and live service state are different

Next movement should be a careful map of which lifecycle docs should move under
this package and which should remain root operator docs.

