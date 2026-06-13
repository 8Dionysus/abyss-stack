# Observability OTLP Tempo Trace Plane

- Decision ID: ABYSS-STACK-D-0070
- Status: accepted
- Date: 2026-06-13
- Owner surface: `compose/modules/60-monitoring.yml`

## Index Metadata

- Original date: 2026-06-13
- Surface classes: runtime/topology, profile/public-contract
- Stack lanes: observability, service selection, config projection
- Mechanic parents: runtime-lifecycle, config-projection
- Guard families: profile-topology, service-selection, source-structure
- Posture: accepted trace-plane observability rationale

## Context

ABYSS-STACK-D-0065 added Loki and Alloy so the explicit `observability` profile
could carry logs next to Prometheus metrics. Runtime agent flows now also need a
bounded trace plane for thread, checkpoint, and span correlation without
committing live traces, prompts, answers, or service logs into source truth.

The stack needs this as an opt-in observability surface, not as a new default
substrate dependency.

## Options considered

- Keep runtime trace inventory as service-local JSON only.
- Send traces directly from services to an external or host-global collector.
- Add Tempo to the existing explicit observability profile and let Alloy expose
  localhost-only OTLP ingest that forwards to Tempo.

## Decision

Choose the Tempo plus Alloy OTLP route inside the explicit `observability`
profile.

Tempo is a localhost-only trace backend with internal OTLP ingest from Alloy.
Alloy keeps the OTLP HTTP/gRPC ingest surface bounded to localhost and forwards
to Tempo. Runtime services may emit redacted trace spans and keep compact local
inventory under stack logs, but raw prompts, answers, advisory payloads,
credentials, and live logs stay out of source.

## Rationale

This extends the existing observability lane from metrics and logs into traces
without widening the default runtime base. It also keeps the collector family
coherent: Alloy handles both log ingestion and OTLP ingress, while Grafana is
the normal operator entry for Prometheus, Loki, and Tempo.

The source checkout owns module shape, public-safe config templates, probe
contracts, and docs. Deployed runtime storage, retention data, live traces,
service restarts, and datasource health remain runtime/operator concerns.

## Consequences

- Positive: agent runtime flows can correlate redacted spans, thread/checkpoint
  inventory, metrics, and logs through the observability profile.
- Tradeoff: live trace value still depends on operator-approved deployment and
  datasource health; source validation can prove shape but not live ingestion.
- Follow-up: after controlled live apply, verify Tempo health, Alloy OTLP
  forwarding, Grafana datasource status, and a representative trace lookup.

## Source surfaces

- `compose/modules/60-monitoring.yml`
- `compose/tuning/observability.thin-host.yml`
- `config-templates/Configs/monitoring/tempo/tempo.yml`
- `config-templates/Configs/monitoring/alloy/config.alloy`
- `config-templates/Configs/monitoring/grafana/provisioning/datasources/00-tempo.yml`
- `config-templates/Services/langchain-api/app/main.py`
- `docs/runtime/SERVICE_CATALOG.md`
- `docs/runtime/service-inventory-2026-05-14.v1.json`
- `docs/runtime/service-selection-policy.v1.json`
- `mechanics/runtime-lifecycle/parts/wait-smoke/aoa_internal_probes.sh`

## Follow-up route

Run:

```bash
python scripts/validate_stack.py
python scripts/ci_gate.py --mode source-fast
python -m pytest mechanics/runtime-lifecycle/parts/logs-status/tests/test_service_selection_policy_validation.py -q
```

Use the controlled source-to-runtime route before claiming live Tempo/OTLP
availability.
