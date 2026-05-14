# Runtime Lifecycle Parts

Runtime-lifecycle parts separate install layout, config sync, start/stop,
readiness, status readouts, and systemd user unit routes.

- [layout-install](layout-install/README.md)
- [first-run-bootstrap](first-run-bootstrap/README.md)
- [config-sync-boundary](config-sync-boundary/README.md)
- [start-stop](start-stop/README.md)
- [wait-smoke](wait-smoke/README.md)
- [logs-status](logs-status/README.md)
- [status-readouts](status-readouts/README.md)
- [user-unit](user-unit/README.md)

Packet routes:

- [source runtime parity](config-sync-boundary/docs/SOURCE_RUNTIME_PARITY_PACKET.md)
- [live runtime cutover](start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md)
