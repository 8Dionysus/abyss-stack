# Observability LogQL Loki Alloy

- Decision ID: ABYSS-STACK-D-0065
- Status: accepted
- Date: 2026-06-04
- Owner surface: `compose/modules/60-monitoring.yml`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: runtime/topology, profile/public-contract
- Stack lanes: observability, service selection, config projection
- Mechanic parents: runtime-lifecycle, config-projection
- Guard families: profile-topology, service-selection, source-structure
- Posture: accepted runtime topology rationale

## Context

`abyss-stack` already carried Prometheus, Grafana, Alertmanager, and cAdvisor,
but that only covered metrics and dashboards. OS Abyss needs logs and metrics to
meet in the same operator route so runtime failures can be investigated through
PromQL and LogQL without turning live logs into source truth.

The current host uses rootless Podman with the journald log driver. A new log
route therefore has to ingest journald entries first while preserving a
file-log fallback for hosts that use file-backed Podman logs.

## Options considered

- Add only Loki:
  This would make LogQL technically available, but it would not ingest stack
  logs and would create an empty observability surface.
- Add Loki plus Promtail:
  This would match older examples, but Promtail is no longer the right new
  collector route for the current Grafana stack.
- Add Loki plus Grafana Alloy:
  This adds a current collector, supports journald and file sources, keeps the
  log path internal-only, and lets Grafana become the normal LogQL entry.

## Decision

The `observability` profile now carries Loki and Grafana Alloy alongside
Prometheus, Grafana, Alertmanager, and cAdvisor.

Loki is internal-only and stores bounded LogQL data in a runtime volume. Alloy
is internal-only and ingests rootless Podman journald entries into Loki, with a
file-log fallback in the public-safe template for hosts that use a file log
driver.

Prometheus scrapes Loki, Alloy, and Grafana metrics. Grafana provisions both
Prometheus and Loki datasources. The `observability.thin-host` overlay bounds
Loki and Alloy resources with the rest of the observability layer.

## Rationale

This route keeps observability as an explicit profile instead of silently
growing the `substrate` base. It also keeps LogQL behind Grafana and internal
network paths, avoiding a new host-facing Loki port.

Alloy is the better fit than Promtail for new source shape because it supports
the current Grafana collector route and can represent both the live host's
journald driver and the fallback file-tail case without adding a second
collector family later.

The source checkout defines the runtime shape and public-safe templates. The
deployed runtime still owns live logs, retention data, container images, and
service restart timing.

## Consequences

- Positive:
  Operators can use Grafana Explore for PromQL and LogQL in the same
  observability profile.
- Tradeoff:
  The first slice does not parse Podman compose labels into stable Loki service
  labels yet; query by `source`, `runtime`, `container`, `podman_name`,
  `podman_type`, `syslog_identifier`, and text such as `name=rag-api` until a
  reviewed parser pass is added.
- Follow-up:
  After controlled live apply, verify Loki datasource health, Alloy ingestion
  counters, and a representative LogQL query against current Podman journal
  entries.

## Source surfaces

- `compose/modules/60-monitoring.yml`
- `compose/tuning/observability.thin-host.yml`
- `config-templates/Configs/monitoring/loki/loki.yml`
- `config-templates/Configs/monitoring/alloy/config.alloy`
- `config-templates/Configs/monitoring/grafana/provisioning/datasources/loki.yml`
- `config-templates/Configs/monitoring/prometheus.yml`
- `docs/runtime/service-selection-policy.v1.json`
- `mechanics/runtime-lifecycle/parts/wait-smoke/docs/INTERNAL_PROBES.md`

## Follow-up route

Use source validation first. Live deployment belongs to the controlled
source-to-runtime route: sync/bootstrap configs, recreate the observability
profile during an operator-approved service window, then run `aoa-smoke
--with-internal` plus explicit Grafana/Loki/Alloy readout checks.
