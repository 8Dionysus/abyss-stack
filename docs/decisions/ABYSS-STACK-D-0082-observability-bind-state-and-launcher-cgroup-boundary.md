# Observability Bind State and Launcher Cgroup Boundary

- Decision ID: ABYSS-STACK-D-0082
- Status: accepted
- Date: 2026-07-18
- Owner surface: `mechanics/runtime-lifecycle/`

## Index Metadata

- Original date: 2026-07-18
- Surface classes: runtime storage, lifecycle, host ingress
- Stack lanes: runtime lane, operations lane
- Mechanic parents: runtime-lifecycle
- Guard families: SELinux mount labeling, explicit teardown, host ingress
- Posture: accepted repair rationale

## Context

Rootless Podman Compose created the observability named volumes without carrying
their declared private `:Z` relabel option into the container mount request.
After container recreation, stale private MCS labels made observability startup
fail before the existing post-start relabel guard could run.

The same failed oneshot launcher then entered the distribution stop-timeout
path. Its control-group kill removed `rootlessport` helpers even though the
payload containers survived or restarted, leaving healthy in-container
services unreachable from their published loopback ports.

## Options considered

- Keep named volumes and repair their labels after every successful start.
- Relabel the entire rootless Podman graphroot through a host-global file
  context rule.
- Move observability persistence to stack-owned bind directories with explicit
  private relabeling, and keep systemd failure cleanup from sweeping Podman
  runtime helpers outside the explicit stack teardown route.

## Decision

Persistent Prometheus, Alertmanager, Loki, Tempo, Alloy, and Grafana state
lives under `Services/monitoring/` and is mounted with explicit `:Z` bind
contracts. Layout install creates those directories and selection-aware layout
validation requires them whenever `60-monitoring.yml` is active.

The `podman-compose-abyss.service` unit and its source-managed late lifecycle
drop-in delegate the runtime cgroup, use `KillMode=process`, and override
stop-timeout failure escalation with `TimeoutStopFailureMode=terminate`.
`aoa-install-systemd` links that drop-in next to the live unit so
distribution-wide user-service defaults cannot supersede the stack boundary.
`aoa-down` remains the explicit owner of container teardown.

This decision does not authorize a graphroot-wide SELinux relabel. Existing
named volumes may be retained outside source as bounded migration rollback
material until the operator verifies the bind-backed runtime.

## Rationale

The bind route makes the persistent-state owner and SELinux relabel intent
visible in both source and rendered container mounts. It removes a
post-success repair dependency from a startup path that can fail before the
repair executes.

The lifecycle route separates launcher failure from payload teardown. Stack
containers still stop through the checked-in `aoa-down` command, while a
launcher timeout cannot independently destroy host ingress for containers that
remain alive. Avoiding a graphroot-wide relabel keeps unrelated rootless
containers and host-owned storage policy outside this bounded stack repair.

## Consequences

- Positive: observability recreation receives the intended private SELinux
  labels at mount creation time.
- Positive: persistent monitoring state remains visible under the canonical
  stack runtime tree and can be copied or backed up explicitly.
- Positive: a failed launcher no longer turns surviving containers into
  host-unreachable payloads by sweeping their port helpers.
- Tradeoff: migration from existing named volumes must preserve numeric
  ownership while the affected stack containers are stopped.
- Tradeoff: `KillMode=process` relies on `aoa-down` as the authoritative
  teardown path; operators must not replace it with implicit cgroup cleanup.
- Follow-up: the host storage owner may separately decide whether the relocated
  rootless graphroot needs a durable SELinux file-context equivalence rule.

## Source surfaces

- `compose/modules/60-monitoring.yml`
- `mechanics/runtime-lifecycle/parts/layout-install/aoa_install_layout.sh`
- `mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `systemd/user/podman-compose-abyss.service`
- `systemd/user/podman-compose-abyss.service.d/99-runtime-lifecycle.conf`
- `docs/runtime/STORAGE_LAYOUT.md`
- `docs/operations/LIFECYCLE.md`

## Follow-up route

Revisit this decision if Podman Compose preserves named-volume SELinux relabel
options end to end, if container lifecycle moves under native generated
systemd units, or if the host storage owner admits a narrower graphroot label
contract that makes bind-level relabeling unnecessary.
