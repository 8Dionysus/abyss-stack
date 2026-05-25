# Decisions District

This district holds decision records explaining why a route, owner split,
runtime topology, validator authority, public contract, or workflow expectation
was chosen in `abyss-stack`.

Decision records explain why; current source surfaces define what.

## District Law

Keep this district reviewable and labeled. A reader or agent should know that a
file here is durable rationale, not current runtime law, generated evidence,
live machine state, or release history.

Use [AGENTS.md](AGENTS.md) for local editing law and [TEMPLATE.md](TEMPLATE.md)
for new records.

## Current Surfaces

| Surface | Role |
|---|---|
| [AGENTS.md](AGENTS.md) | local decision-record route card |
| [TEMPLATE.md](TEMPLATE.md) | required record shape for new decisions |
| [2026-05-07 Runtime Root Under AbyssOS](2026-05-07-runtime-root-under-abyssos.md) | decision record for the deployed runtime root |
| [2026-05-07 Runtime Mechanics Topology](2026-05-07-runtime-mechanics-topology.md) | decision record for the runtime mechanics tree |
| [2026-05-07 Mechanics Legacy Artifact Containment](2026-05-07-mechanics-legacy-artifact-containment.md) | decision record for package-local legacy containment |
| [2026-05-12 Machine Bridge Under Machine Fit](2026-05-12-machine-bridge-under-machine-fit.md) | decision record for the read-only machine bridge home |
| [2026-05-12 Operator Wrappers With Part-Local Backends](2026-05-12-operator-wrappers-with-part-local-backends.md) | decision record for stable root wrappers and part-local backends |
| [2026-05-13 Local AI Trials First-Run Boundary](2026-05-13-local-ai-trials-first-run-boundary.md) | decision record for separating first-run bootstrap from model trials |
| [2026-05-13 Inference Pilot Compatibility Gates](2026-05-13-inference-pilot-compatibility-gates.md) | decision record for inference-pilot compatibility IDs |
| [2026-05-13 Root Design And Agent Surfaces](2026-05-13-root-design-agent-surfaces.md) | decision record for root design and agent-surface design files |
| [2026-05-13 Root Residual Topology Cleanup](2026-05-13-root-residual-topology-cleanup.md) | decision record for moving audit and Spark residuals to owning districts |
| [2026-05-13 Workspace Sibling Roots Under AbyssOS](2026-05-13-workspace-sibling-roots-under-abyssos.md) | decision record for active sibling workspace roots |
| [2026-05-13 Legacy-Heavy Runtime Package Distillation](2026-05-13-legacy-heavy-runtime-package-distillation.md) | decision record for Agon and Experience runtime package distillation |
| [2026-05-13 Quest And Compatibility Topology](2026-05-13-quest-and-compatibility-topology.md) | decision record for quest lane/state topology and compatibility routes |
| [2026-05-13 Runtime Compatibility Boundaries](2026-05-13-runtime-compatibility-boundaries.md) | decision record for upstream compatibility boundary handling |
| [2026-05-13 Residual Frontier Quest Alignment](2026-05-13-residual-frontier-quest-alignment.md) | decision record for evidence-based quest frontier alignment |
| [2026-05-13 Mechanics Package Card Completeness](2026-05-13-mechanics-package-card-completeness.md) | decision record for the full mechanics package-card spine |
| [2026-05-13 Live Runtime Cutover And Machine Parity](2026-05-13-live-runtime-cutover-parity.md) | decision record for parity and cutover packet surfaces |
| [2026-05-14 Direction, History, And Decision Surface Roles](2026-05-14-direction-history-decision-surface-roles.md) | decision record for the `README.md`, `ROADMAP.md`, `CHANGELOG.md`, and `docs/decisions/` role split |
| [2026-05-14 Entry Route Contract And Validation Placement](2026-05-14-entry-route-contract-validation-placement.md) | decision record for the root entry route contract and README validation placement |
| [2026-05-14 GitHub Homepage README Selection](2026-05-14-github-homepage-readme-selection.md) | decision record for keeping `.github/` from replacing the root homepage README |
| [2026-05-14 Docs District Topology](2026-05-14-docs-district-topology.md) | decision record for replacing flat root docs with role-named districts |
| [2026-05-14 Source Component Pinning Posture](2026-05-14-source-component-pinning-posture.md) | decision record for current source component pins without hidden stateful major migration |
| [2026-05-14 Machine Evidence Freshness Gates](2026-05-14-machine-evidence-freshness-gates.md) | decision record for stack-side freshness gates over read-only machine evidence |
| [2026-05-14 Working Substrate Profile](2026-05-14-working-substrate-profile.md) | decision record for making `substrate` the source-owned default runtime base |
| [2026-05-14 Fallback Gateway Profile](2026-05-14-fallback-gateway-profile.md) | decision record for keeping retained Ollama/LiteLLM behind an explicit profile |
| [2026-05-14 Composition-First Presets](2026-05-14-composition-first-presets.md) | decision record for making named presets expand through explicit substrate and worker layers |
| [2026-05-14 Workflow Automation Optional Profile](2026-05-14-workflow-automation-optional-profile.md) | decision record for keeping n8n behind an explicit `workflows` profile |
| [2026-05-14 Managed Systemd Unit Sources](2026-05-14-managed-systemd-unit-sources.md) | decision record for source-managed user and system unit skeleton allowlists |
| [2026-05-15 Intel Inference And Rerank Service Selection](2026-05-15-intel-inference-and-rerank-service-selection.md) | decision record for Gemma 4 E2B, OVMS embeddings, Qwen3 reranking, and protected TTS service selection |
| [2026-05-15 BabelVox TTS Experimental Lane](2026-05-15-babelvox-tts-experimental-lane.md) | decision record for keeping BabelVox as an opt-in Intel speech experiment |
| [2026-05-16 RAG Orchestration Profile](2026-05-16-rag-orchestration-profile.md) | decision record for the lightweight RAG orchestration profile over existing stack stores and model lanes |
| [2026-05-20 AoA Memo MCP Under Stack MCP](2026-05-20-aoa-memo-mcp-under-stack-mcp.md) | superseded first-landing decision for placing the memory MCP access plane under stack MCP |
| [2026-05-20 MCP Services Topology](2026-05-20-mcp-services-topology.md) | decision record for the canonical `mcp/services/aoa-memo-mcp` topology |
| [2026-05-21 AoA Memo MCP Port Confinement](2026-05-21-aoa-memo-mcp-port-confinement.md) | decision record for schema-backed, port-confined MCP packet handling |
| [2026-05-22 AoA Memo MCP Landing Plan Boundary](2026-05-22-aoa-memo-mcp-landing-plan-boundary.md) | decision record for exposing pending-export and landing-plan helpers without making MCP a durable memory writer |
| [2026-05-25 AoA Evals MCP Access Plane](2026-05-25-aoa-evals-mcp-access-plane.md) | decision record for the stack-owned, read-only `aoa_evals` MCP service over `aoa-evals` proof surfaces |

## Record Shape

New records must use [TEMPLATE.md](TEMPLATE.md). The standard shape is:

- `Status`
- `Date`
- `Context`
- `Options considered`
- `Decision`
- `Rationale`
- `Consequences`
- `Source surfaces`
- `Follow-up route`

## Must Not Claim

Decisions explain why; current source surfaces define what.

Do not use this district to absorb:

- current runtime direction that belongs in `ROADMAP.md`
- release-visible history that belongs in `CHANGELOG.md`
- mechanic-local direction, provenance, or landings
- live runtime receipts, private captures, logs, secrets, models, or generated
  runtime state
- sibling-owner doctrine from AoA, ToS, skills, techniques, evals, memory,
  routing, KAG, playbooks, stats, agents, or machine repositories

## Validation

Executable validation commands live in [AGENTS](AGENTS.md#validation),
including the `validate_decision_records.py` route. This README describes the
decision-record district; the route card owns the operational command list.
