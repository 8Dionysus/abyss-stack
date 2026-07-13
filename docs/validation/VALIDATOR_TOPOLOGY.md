# Validator Topology

`abyss-stack` validators protect the runtime substrate without becoming live
runtime truth. They check source topology, route cards, generated companions,
operator wrapper contracts, MCP access-plane boundaries, and source/runtime
parity posture.

## Layers

| Layer | Protects | Owner surface | Lane |
|---|---|---|---|
| Command authority | validation lane storage and execution routing | `docs/validation/validation_lanes.json` | source-fast, release |
| Source topology orchestration | route cards, required source surfaces, federation seams, owner-module execution order, and source/runtime guard routing | `scripts/validate_stack.py` | source-fast, release |
| Source structure | required files, managed unit skeletons, residual root/doc district moves | `scripts/validators/source_structure.py` | source-fast, release |
| Mechanics topology | mechanic package cards, part route coverage, package/part required files, archive routes, and marker-only artifact posture | `scripts/validators/mechanics_topology.py` | source-fast, release |
| Source hygiene | public-safe mirror posture, host-local checkout links, stale sibling roots | `scripts/validators/source_hygiene.py` | source-fast, release |
| Runtime profile topology | composition-first profiles and presets, module dependency guards, profile workflow rehearsal, sidecar/n8n/warmup posture, and active route profile language | `scripts/validators/profile_topology.py` | source-fast, release |
| Runtime route contracts | stale runtime-root bans, root README route focus, source/deployed wording, federation handoff docs, and governed policy/catalog envelope | `scripts/validators/runtime_route_contracts.py` | source-fast, release |
| Inference pilot compatibility | active local-trials bridge posture, preserved gate IDs, LangGraph and llama.cpp gate language, and autonomy status legacy-pilot routes | `scripts/validators/inference_pilot_compatibility.py` | source-fast, release |
| Active topology language | retired phase/wave/seed wording, RPG runtime projection language, playbook activation allowlist drift, and route-api active/compatibility bridge language | `scripts/validators/active_topology_language.py` | source-fast, release |
| Agent skill projection | repo-local `.agents/skills` projection, sibling `aoa-skills` symlink targets, checkout-safe target files, and local overlay skill posture | `scripts/validators/agent_skill_projection.py` | source-fast, release |
| Runtime service selection | selected service policy, screenshot inventory, current runtime shape parity | `scripts/validators/service_selection.py` | source-fast, release |
| Source-to-Configs parity | sync-managed item coverage, runtime Configs mirror posture, deployed parity | `scripts/validators/sync_parity.py` | source-fast, release |
| Questbook and RPG read models | quest source topology, generated quest examples, RPG runtime collection schemas | `scripts/validators/questbook_surface.py` | source-fast, release |
| Federation runtime inputs and landing | runtime-loaded federation config input coverage, upstream compatibility bridge posture, landing docs | `scripts/validators/federation_surface.py` | source-fast, release |
| Federation runtime seams | memo/eval/playbook/KAG runtime seam docs, bounded export schemas/examples, advisory route guards | `scripts/validators/federation_runtime_seams.py` | source-fast, release |
| Diagnostic spine contracts | diagnostic surface docs, schemas, examples, catalog refs, and overlay skill posture | `scripts/validators/diagnostic_spine.py` | source-fast, release |
| Runtime hygiene status readouts | gateway cache and usage status readout docs, schemas, examples, and doctor split posture | `scripts/validators/runtime_hygiene.py` | source-fast, release |
| Machine-fit evidence posture | reference platform, host facts, machine bridge, fit record, freshness gates, and platform adaptation public contracts | `scripts/validators/machine_fit.py` | source-fast, release |
| Return-policy runtime contracts | return-policy config routes, render-truth autonomy route, and runtime return policy/event schema identity | `scripts/validators/return_policy.py` | source-fast, release |
| Branch governance | CONTRIBUTING branch route, canonical `main` posture, branch retirement rules, and source/runtime checkout distinction | `scripts/validators/branch_policy.py` | source-fast, release |
| Root design and entry routes | root design cards, route contract exposure, front-door route modes, and command-authority handoff language | `scripts/validators/root_routes.py` | source-fast, release |
| Agent route topology | nested `AGENTS.md` coverage, explicit legacy-archive card classification, and route snippets | `scripts/validate_nested_agents.py` | source-fast, release |
| Decision surface routes | docs/decisions route cards, template requirements, validator/generator handoff, and test route exposure | `scripts/validators/decision_surface.py` | source-fast, release |
| Decision rationale | canonical decision IDs, generated repo graph, local workspace decision graph freshness, and graph schema/coverage contract | `docs/decisions/`, `scripts/build_workspace_decision_graph.py`, `scripts/validate_workspace_decision_graph.py` | source-fast, generated, decision-graph, release |
| Generated diagnostics | diagnostic surface catalog and generated read model | `mechanics/diagnostic-spine/` | generated, release |
| Script surface | root wrappers, part-local backends, MCP scripts, quest helpers, side effects | `docs/validation/script_inventory.json` | source-fast |
| Test surface | root, mechanic part-local, and MCP tests | `docs/testing/test_inventory.json` | tests, release |
| MCP access plane | stack-owned MCP service validators and package tests | `mcp/services/*` | mcp-services, release |
| Source/runtime parity | source checkout against deployed or synthetic `Configs` mirror | `scripts/release_check.py` and `scripts/validate_stack.py --parity-check` | release only |

## Current Split

The split is now module-owned. `scripts/validate_stack.py` is the repo-wide
source-fast and release entrypoint, but it no longer exposes public
`validate_*` compatibility functions for focused owner surfaces. It owns
execution order, runtime Configs mirror mode, deployed parity CLI routing, and
small private callbacks needed to call owner modules. Validator constants and
manifests live with their focused owner modules.

Focused validators own the contracts under `scripts/validators/`. Tests and
route docs should call those modules directly when they need a specific owner
surface. The old compatibility-wrapper period from D-0040 through D-0062 was a
temporary extraction bridge and is closed by D-0063.

Future validator work should follow the same rule: put behavior in the
coherent owner module, keep `scripts/validate_stack.py` as the command
orchestrator, and update inventories plus focused tests without reintroducing
root-level wrapper APIs.

## Root Entry Points

| Entrypoint | Mode | Failure route |
|---|---|---|
| `scripts/ci_gate.py` | lane orchestrator | fix `docs/validation/validation_lanes.json` or the failing lane owner |
| `scripts/release_check.py` | release stabilizer | fix the release lane, then Configs parity if parity fails |
| `scripts/validate_stack.py` | repo-wide validation orchestrator | fix the named owner module or root orchestration glue |
| `scripts/validators/script_surface.py` | root script/operator backend validator module | fix script inventory, operator wrapper routes, or owning mechanic backends |
| `scripts/validators/source_structure.py` | required-file and root residual topology validator module | fix required source surfaces, docs district routing, or systemd skeleton inventory |
| `scripts/validators/mechanics_topology.py` | mechanics topology validator module | fix mechanics atlas routes, package cards, part required files, archive route posture, or focused mechanics-topology tests |
| `scripts/validators/source_hygiene.py` | source/runtime and mirror hygiene validator module | fix public-safe mirror policy, stale path rules, or source-hygiene tests |
| `scripts/validators/profile_topology.py` | runtime profile topology validator module | fix profile/preset contents, compose module requirements, profile docs, workflow rehearsal, sidecar/n8n/warmup posture, or focused profile-topology tests |
| `scripts/validators/runtime_route_contracts.py` | runtime route contract validator module | fix stale runtime-root references, README route focus, runtime/federation route docs, governed policy/catalog envelope, or focused runtime-route tests |
| `scripts/validators/inference_pilot_compatibility.py` | inference pilot compatibility validator module | fix local-trials compatibility bridge posture, gate IDs, legacy metadata containment, pilot docs/code language, or focused inference-pilot tests |
| `scripts/validators/active_topology_language.py` | active topology language validator module | fix retired phase/wave/seed wording, RPG runtime projection language, playbook activation allowlists, route-api bridge language, or focused active-topology tests |
| `scripts/validators/agent_skill_projection.py` | agent skill projection validator module | fix `.agents/skills` symlink/target-file projection, local overlay directories, diagnostic overlay skill installs, or focused agent-skill tests |
| `scripts/validators/service_selection.py` | runtime service-selection policy validator module | fix service-selection policy, screenshot inventory, compose runtime-shape parity, or focused service-selection tests |
| `scripts/validators/sync_parity.py` | source-to-Configs parity validator module | fix config-projection sync coverage, runtime Configs mirror shape, source/deployed parity, or focused sync parity tests |
| `scripts/validators/questbook_surface.py` | questbook and RPG read-model validator module | fix quest source files, generated quest examples, RPG runtime schemas/examples, or focused questbook tests |
| `scripts/validators/federation_surface.py` | federation runtime-input validator module | fix federation config `required_files`, upstream compatibility bridge templates/language, landing docs, or focused federation tests |
| `scripts/validators/federation_runtime_seams.py` | federation runtime seam validator module | fix memo/eval/playbook/KAG seam docs, bounded export examples, A2A handoff examples, or focused federation runtime seam tests |
| `scripts/validators/diagnostic_spine.py` | diagnostic spine contract validator module | fix diagnostic docs, schemas, examples, generated catalog refs, overlay skill posture, or focused diagnostic spine tests |
| `scripts/validators/runtime_hygiene.py` | runtime hygiene status-readout validator module | fix status-readout docs, schemas, examples, doctor split posture, or focused runtime hygiene tests |
| `scripts/validators/machine_fit.py` | machine-fit evidence validator module | fix reference-platform docs, host-facts examples, machine bridge read-only posture, freshness gates, platform-adaptation examples, or focused machine-fit tests |
| `scripts/validators/return_policy.py` | return-policy runtime contract validator module | fix return-policy config routes, render-truth autonomy refs, runtime return schemas, or focused return-policy tests |
| `scripts/validators/branch_policy.py` | branch governance validator module | fix CONTRIBUTING branch route, branch-policy main/retirement language, source/runtime checkout refs, or focused branch-policy tests |
| `scripts/validators/root_routes.py` | root design and entry route validator module | fix root design cards, start-here route exposure, route modes, command-authority handoff text, or focused root-route tests |
| `scripts/validate_nested_agents.py` | AGENTS route topology | fix nearest active `AGENTS.md`, required route doc, or explicit legacy-archive classification |
| `scripts/validators/decision_surface.py` | decision surface route validator module | fix decision route cards, template shape, validator/generator handoff text, or focused decision-surface tests |
| `scripts/validate_decision_records.py` | decision record shape | fix decision metadata or generated decision read models |
| `scripts/build_workspace_decision_graph.py` | local workspace decision graph builder | refresh `Logs/decision-graph/latest/` with `--write` or verify it with `--check`; inspect source-posture warnings and do not treat local cache freshness as repo or remote freshness |
| `scripts/validate_workspace_decision_graph.py` | local workspace graph schema, source-posture, and coverage contract | refresh the graph cache, repair schema enums/counts/posture projection, or model unknown decision-lane surfaces |
| MCP service validators | service-local access-plane checks | fix the service package and owner-boundary docs |

## Must Not Claim

Validators do not prove live service availability unless a lane explicitly
executes a live or synthetic runtime check. They do not own sibling repository
meaning, private host truth, durable memory truth, proof verdicts, or model
evaluation authority.
