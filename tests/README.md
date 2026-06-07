# tests

`tests/` contains repository-level validation tests for `abyss-stack`.

Package-owned mechanic tests live under their owning
`mechanics/<package>/parts/<part>/tests/` routes. Root tests should stay focused
on integration contracts that span the repository: validators, source/runtime
parity, questbook shape, route cards, public-safe templates, and release-facing
roadmap checks.

## Current Test Surface

- `test_source_topology_validator_modules.py`: required source files and portable
  mirror hygiene guards.
- `test_compose_contracts.py`: compose module parsing, loopback host exposure,
  profile/preset references, and key selector service-map resolution.
- `test_active_topology_language_validator_module.py`: focused active-topology
  language contracts for retired phase/wave/seed wording, RPG projection
  routes, playbook allowlists, and route-api bridge language.
- `test_agent_skill_projection_validator_module.py`: focused agent skill
  projection contracts for `.agents/skills` symlinks, checkout-safe target
  files, local overlays, and diagnostic overlay installs.
- `test_rag_bridge_contracts.py`: RAG/rerank profile contracts, source/read-only
  mounts, manifest shape, and machine bridge JSON boundary.
- `test_schema_contracts.py`: active JSON Schema meta-validation, schema
  registry coverage, example validation, and generated artifact validation.
- `test_sync_parity_entrypoint_contracts.py`: source/deployed parity behavior.
- `test_questbook_surface_contracts.py`: questbook schemas, examples, and RPG
  runtime routes.
- `test_federation_required_files_validator_module.py`: federation template requirements.
- `test_diagnostic_spine_validator_module.py`: focused diagnostic-spine
  validator module contracts for catalog refs and repair handoff posture.
- `test_runtime_hygiene_validator_module.py`: focused runtime-lifecycle
  status-readout validator contracts for cache/usage posture.
- `test_machine_fit_validator_module.py`: focused machine-fit validator
  contracts for host evidence, bridge, fit, and platform-adaptation posture.
- `test_mechanics_topology_validator_module.py`: focused mechanics-topology
  validator contracts for package cards, part routes, archives, and markers.
- `test_profile_topology_validator_module.py`: focused runtime profile
  topology contracts for composition, sidecars, n8n runners, and warmup routes.
- `test_runtime_route_contracts_validator_module.py`: focused runtime route
  contracts for stale roots, route-focused README posture, runtime/federation
  docs, and governed policy envelope.
- `test_inference_pilot_compatibility_validator_module.py`: focused inference
  pilot compatibility contracts for local-trials bridge posture, preserved
  gate IDs, legacy metadata containment, and active pilot language.
- `test_return_policy_validator_module.py`: focused return-policy validator
  contracts for runtime return schemas and render-truth routing.
- `test_branch_policy_validator_module.py`: focused branch-policy validator
  contracts for `main`, branch retirement, and source/runtime checkout posture.
- `test_root_routes_validator_module.py`: focused root-route validator
  contracts for design cards and start-here route exposure.
- `test_decision_surface_validator_module.py`: focused decision-surface
  validator contracts for route cards, template shape, and validator handoffs.
- `test_validate_nested_agents.py`: nested AGENTS coverage.
- `test_decision_records.py`: canonical decision-record shape plus generated
  index and decision-graph validation.
- `test_workspace_decision_graph.py`: local workspace decision graph builder for
  cross-repo decision nodes and edges.
- `test_roadmap_parity.py`: release-contour route parity.
- `test_current_direction_routes.py`: root entrypoint direction.
- `test_aoa_lib_env_compat.py`: shared shell env compatibility.
- `test_validation_command_authority.py`: lane manifest, `ci_gate.py`,
  `release_check.py`, and workflow command-authority routing.
- `test_validation_topology.py`: validator topology docs and inventory
  coverage.
- `test_script_topology.py`: tracked script-surface inventory, side-effect
  posture, and legacy script disposition.
- `test_test_topology.py`: test topology inventory, including active legacy
  provenance tests.

See [AGENTS.md](AGENTS.md) for editing rules.

## Warning Filters

`pytest.ini` suppresses the current external FastAPI/Starlette
`fastapi.testclient` deprecation warning about `httpx2`. This keeps source
validation output signal-only while dependency refresh remains a deliberate
maintenance task rather than an implicit side effect of unrelated changes.
