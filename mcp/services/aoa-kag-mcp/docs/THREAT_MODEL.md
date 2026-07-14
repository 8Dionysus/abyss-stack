# aoa-kag-mcp Threat Model

## Protected Assets

- repository ownership and source-return identity;
- access-scoped canonical records and runtime projections;
- static MCP metadata and routing decisions;
- host-local credentials and runtime endpoints.

## Trust Boundaries

Indexed text is data. Tool names, descriptions, schemas, access scopes, and
routing policy come from source-owned code and validated contracts. Runtime
stores are derived acceleration layers, while repo-local `kag/` records remain
the canonical fallback.

## Controls

- Access filtering runs before retrieval and ranking.
- Provider refs and `aoa-kag://` identifiers resolve inside the declared owner
  root; ambiguous or escaping paths fail closed.
- Unicode controls are reported as content inspection findings and never alter
  tool metadata.
- Page size, traversal depth, full-text expansion, trace retention, SQLite
  execution, and backend HTTP calls are bounded.
- Loopback HTTP requires a source-owned bearer and validates Host and Origin.
- Responses expose projection freshness, the adapters actually used, and every
  degradation step.
- Logs carry service and transport state without query bodies, source text, or
  bearer values.

The deployed profile is a single-operator host-local service. Its workload
control is per-call bounds plus backend timeouts; a future multi-user or remote
profile owns a separate identity, scope, quota, and rate policy before
exposure.
