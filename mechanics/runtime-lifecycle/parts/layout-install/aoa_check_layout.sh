#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

strict_mode=0
ignore_secrets=0
selector_args=()
while (($#)); do
  case "$1" in
    --strict)
      strict_mode=1
      ;;
    --ignore-secrets)
      ignore_secrets=1
      ;;
    --preset|--profile)
      option_name="$1"
      selector_args+=("$1")
      shift || true
      (($#)) || aoa_die "missing value after ${option_name}"
      selector_args+=("$1")
      ;;
    --preset=*|--profile=*)
      selector_args+=("$1")
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

errors=0
warnings=0

check_dir() {
  local path="$1"
  if [[ -d "$path" ]]; then
    aoa_note "ok   dir  $path"
  else
    aoa_note "fail dir  $path"
    errors=$((errors + 1))
  fi
}

check_file() {
  local label="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    aoa_note "ok   file $label -> $path"
  else
    aoa_note "fail file $label -> $path"
    errors=$((errors + 1))
  fi
}

check_warn_file() {
  local label="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    aoa_note "ok   file $label -> $path"
  else
    aoa_note "warn file $label -> $path"
    warnings=$((warnings + 1))
  fi
}

AOA_UPSTREAM_COMPATIBILITY_BRIDGE_CONFIG="${AOA_CONFIGS_ROOT}/federation/upstream-compatibility-bridge.json"

compatibility_bridge_value() {
  local query="$1"
  if [[ ! -f "${AOA_UPSTREAM_COMPATIBILITY_BRIDGE_CONFIG}" ]]; then
    printf '__missing_upstream_compatibility_bridge__/%s\n' "$query"
    return 0
  fi
  python3 - "${AOA_UPSTREAM_COMPATIBILITY_BRIDGE_CONFIG}" "$query" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
value = payload
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}

AOA_EVALS_MEMO_RECALL_UPSTREAM_TEMPLATE="$(
  compatibility_bridge_value "runtime_evidence_templates.memo-recall-rerun.upstream_source_ref"
)"
AOA_EVALS_MEMO_CONTRADICTION_GAP_UPSTREAM_TEMPLATE="$(
  compatibility_bridge_value "runtime_evidence_templates.memo-contradiction-gap.upstream_source_ref"
)"
AOA_EVALS_MEMO_CONTRADICTION_RERUN_UPSTREAM_TEMPLATE="$(
  compatibility_bridge_value "runtime_evidence_templates.memo-contradiction-rerun.upstream_source_ref"
)"
AOA_PLAYBOOKS_AUTOMATION_PLANS_UPSTREAM_FILE="$(
  compatibility_bridge_value "playbook_automation_plans.upstream_rel_path"
)"

has_module() {
  local target="$1"
  local module

  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

selection_metadata_ready=0
if [[ -d "${AOA_PROFILES_DIR}" ]] && [[ -d "${AOA_MODULES_DIR}" ]]; then
  selection_metadata_ready=1
  aoa_parse_profile_args "${selector_args[@]}"
  aoa_resolve_modules
else
  aoa_note "skip selection-sensitive checks until synced compose metadata exists under ${AOA_CONFIGS_ROOT}"
fi

required_dirs=(
  "${AOA_STACK_ROOT}/Configs"
  "${AOA_STACK_ROOT}/Secrets/Configs"
  "${AOA_STACK_ROOT}/Services"
  "${AOA_STACK_ROOT}/Models"
  "${AOA_STACK_ROOT}/Knowledge"
  "${AOA_STACK_ROOT}/Logs"
)

for path in "${required_dirs[@]}"; do
  check_dir "$path"
done

if ((ignore_secrets)); then
  aoa_note "skip secret file checks on this pass"
else
  check_warn_file "stack env" "${AOA_STACK_ROOT}/Configs/stack.env"
  check_warn_file "langchain env" "${AOA_STACK_ROOT}/Secrets/Configs/langchain-api.env"
  check_warn_file "ovms env" "${AOA_STACK_ROOT}/Secrets/Configs/ovms-api.env"
  check_warn_file "ovms key file" "${AOA_STACK_ROOT}/Secrets/Configs/ovms_api_key.txt"
fi

check_warn_file "prometheus config" "${AOA_STACK_ROOT}/Configs/monitoring/prometheus.yml"
check_warn_file "alert rules" "${AOA_STACK_ROOT}/Configs/monitoring/alerts.yml"
check_warn_file "alertmanager config" "${AOA_STACK_ROOT}/Configs/monitoring/alertmanager/alertmanager.yml"
check_warn_file "grafana datasource" "${AOA_STACK_ROOT}/Configs/monitoring/grafana/provisioning/datasources/prometheus.yml"
check_warn_file "grafana loki datasource" "${AOA_STACK_ROOT}/Configs/monitoring/grafana/provisioning/datasources/loki.yml"
check_warn_file "grafana tempo datasource" "${AOA_STACK_ROOT}/Configs/monitoring/grafana/provisioning/datasources/00-tempo.yml"
check_warn_file "loki config" "${AOA_STACK_ROOT}/Configs/monitoring/loki/loki.yml"
check_warn_file "tempo config" "${AOA_STACK_ROOT}/Configs/monitoring/tempo/tempo.yml"
check_warn_file "alloy config" "${AOA_STACK_ROOT}/Configs/monitoring/alloy/config.alloy"
check_warn_file "tts voices" "${AOA_STACK_ROOT}/Configs/tts/voices.yaml"
check_warn_file "litellm config" "${AOA_STACK_ROOT}/Services/litellm/config.yaml"
check_dir "${AOA_STACK_ROOT}/Logs/machine-bridge/latest"
check_dir "${AOA_STACK_ROOT}/Logs/machine-bridge/records"
check_dir "${AOA_STACK_ROOT}/Logs/diagnostics/latest"
check_dir "${AOA_STACK_ROOT}/Logs/diagnostics/records"
check_dir "${AOA_STACK_ROOT}/Logs/rpg/latest"
check_dir "${AOA_STACK_ROOT}/Logs/rpg/records"

if ((selection_metadata_ready)) && has_module "41-agent-api.yml"; then
  aoa_note "selected runtime includes 41-agent-api.yml; checking return-policy contract"
  check_dir "${AOA_STACK_ROOT}/Logs/returns"
  check_dir "${AOA_STACK_ROOT}/Logs/governed-runs"
  check_dir "${AOA_STACK_ROOT}/Logs/langgraph-inventory"
  check_warn_file "agent API return policy" "${AOA_STACK_ROOT}/Configs/agent-api/return-policy.yaml"
  check_warn_file "agent API governed execution policy" "${AOA_STACK_ROOT}/Configs/agent-api/governed-execution-policy.yaml"
  check_warn_file "agent API governed canary catalog" "${AOA_STACK_ROOT}/Configs/agent-api/governed-canary-catalog.json"
fi

if ((selection_metadata_ready)) && has_module "20-orchestration.yml"; then
  aoa_note "selected runtime includes 20-orchestration.yml; checking optional workflow automation layout"
  check_dir "${AOA_STACK_ROOT}/Services/n8n"
  check_dir "${AOA_STACK_ROOT}/Knowledge/n8n-docs"
fi

if ((selection_metadata_ready)) && has_module "43-federation-router.yml"; then
  aoa_note "selected runtime includes 43-federation-router.yml; checking aoa-agents, aoa-routing, aoa-memo, aoa-evals, aoa-playbooks, aoa-kag, and tos-source federation mirrors"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag"
  check_dir "${AOA_STACK_ROOT}/Knowledge/federation/tos-source"
  check_dir "${AOA_STACK_ROOT}/Logs/eval-exports/latest/runtime-evidence-selection"
  check_dir "${AOA_STACK_ROOT}/Logs/eval-exports/latest/artifact-hook"
  check_dir "${AOA_STACK_ROOT}/Logs/eval-exports/records"
  check_dir "${AOA_STACK_ROOT}/Logs/memo-exports/latest"
  check_dir "${AOA_STACK_ROOT}/Logs/memo-exports/records"
  check_warn_file "aoa-agents federation config" "${AOA_STACK_ROOT}/Configs/federation/aoa-agents.yaml"
  check_warn_file "aoa-routing federation config" "${AOA_STACK_ROOT}/Configs/federation/aoa-routing.yaml"
  check_warn_file "aoa-memo federation config" "${AOA_STACK_ROOT}/Configs/federation/aoa-memo.yaml"
  check_warn_file "aoa-evals federation config" "${AOA_STACK_ROOT}/Configs/federation/aoa-evals.yaml"
  check_warn_file "aoa-playbooks federation config" "${AOA_STACK_ROOT}/Configs/federation/aoa-playbooks.yaml"
  check_warn_file "aoa-kag federation config" "${AOA_STACK_ROOT}/Configs/federation/aoa-kag.yaml"
  check_warn_file "tos-source federation config" "${AOA_STACK_ROOT}/Configs/federation/tos-source.yaml"
  check_warn_file "upstream compatibility bridge config" "${AOA_UPSTREAM_COMPATIBILITY_BRIDGE_CONFIG}"
  check_warn_file "aoa-agents role-tier runtime seam doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/mechanics/runtime-seam/parts/role-tier-bindings/docs/agent-runtime-seam.md"
  check_warn_file "aoa-agents runtime transition doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/mechanics/runtime-seam/parts/transition-discipline/docs/runtime-artifact-transitions.md"
  check_warn_file "aoa-agents agent registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/generated/agent_registry.min.json"
  check_warn_file "aoa-agents tier registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/generated/model_tier_registry.json"
  check_warn_file "aoa-agents seam bindings" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/generated/runtime_seam_bindings.json"
  check_warn_file "aoa-agents cohort registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/generated/cohort_composition_registry.json"
  check_warn_file "aoa-agents agent registry schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/schemas/agent-registry.schema.json"
  check_warn_file "aoa-agents model tier schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/schemas/model-tier-registry.schema.json"
  check_warn_file "aoa-agents seam bindings schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/schemas/runtime-seam-bindings.schema.json"
  check_warn_file "aoa-agents cohort schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/schemas/cohort-composition-registry.schema.json"
  check_warn_file "aoa-agents route decision artifact schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents/mechanics/runtime-seam/parts/artifact-contracts/schemas/artifact.route_decision.schema.json"
  check_warn_file "aoa-routing federation ABI doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/docs/FEDERATION_ENTRY_ABI.md"
  check_warn_file "aoa-routing recurrence boundary doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/docs/RECURRENCE_NAVIGATION_BOUNDARY.md"
  check_warn_file "aoa-routing router surface" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/aoa_router.min.json"
  check_warn_file "aoa-routing cross repo registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/cross_repo_registry.min.json"
  check_warn_file "aoa-routing surface hints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/task_to_surface_hints.json"
  check_warn_file "aoa-routing tier hints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/task_to_tier_hints.json"
  check_warn_file "aoa-routing recommended paths" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/recommended_paths.min.json"
  check_warn_file "aoa-routing pairing hints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/pairing_hints.min.json"
  check_warn_file "aoa-routing kag relation hints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/kag_source_lift_relation_hints.min.json"
  check_warn_file "aoa-routing federation entrypoints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/federation_entrypoints.min.json"
  check_warn_file "aoa-routing return hints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/return_navigation_hints.min.json"
  check_warn_file "aoa-routing tiny-model entrypoints" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/generated/tiny_model_entrypoints.json"
  check_warn_file "aoa-routing router schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/aoa-router.schema.json"
  check_warn_file "aoa-routing cross repo schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/cross-repo-registry.schema.json"
  check_warn_file "aoa-routing task-to-surface schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/task-to-surface-hints.schema.json"
  check_warn_file "aoa-routing task-to-tier schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/task-to-tier-hints.schema.json"
  check_warn_file "aoa-routing recommended paths schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/recommended-paths.schema.json"
  check_warn_file "aoa-routing pairing schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/pairing-hints.schema.json"
  check_warn_file "aoa-routing kag relation schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/kag-source-lift-relation-hints.schema.json"
  check_warn_file "aoa-routing federation entrypoints schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/federation-entrypoints.schema.json"
  check_warn_file "aoa-routing return hints schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/return-navigation-hints.schema.json"
  check_warn_file "aoa-routing tiny-model entrypoints schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/tiny-model-entrypoints.schema.json"
  check_warn_file "aoa-routing router entry schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing/schemas/router-entry.schema.json"
  check_warn_file "aoa-memo memory model doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/docs/memory/MEMORY_MODEL.md"
  check_warn_file "aoa-memo runtime writeback seam doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/writeback/docs/RUNTIME_WRITEBACK_SEAM.md"
  check_warn_file "aoa-memo recurrence support doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/recurrence-support/docs/RECURRENCE_MEMORY_SUPPORT_SURFACES.md"
  check_warn_file "aoa-memo agent posture seam doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/consumer-handoff/docs/AGENT_MEMORY_POSTURE_SEAM.md"
  check_warn_file "aoa-memo playbook scopes doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/consumer-handoff/docs/PLAYBOOK_MEMORY_SCOPES.md"
  check_warn_file "aoa-memo registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/generated/memory/memo_registry.min.json"
  check_warn_file "aoa-memo catalog" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/generated/memory/memory_catalog.min.json"
  check_warn_file "aoa-memo sections" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/generated/memory/memory_sections.full.json"
  check_warn_file "aoa-memo object catalog" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/generated/memory-objects/memory_object_catalog.min.json"
  check_warn_file "aoa-memo object sections" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/generated/memory-objects/memory_object_sections.full.json"
  check_file "aoa-memo runtime writeback targets" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/writeback/parts/runtime-and-temperature/generated/runtime_writeback_targets.min.json"
  check_file "aoa-memo runtime writeback intake" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/writeback/parts/runtime-and-temperature/generated/runtime_writeback_intake.min.json"
  check_warn_file "aoa-memo checkpoint contract example" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/checkpoint/parts/checkpoint-to-memory-mapping/examples/checkpoint_to_memory_contract.example.json"
  check_warn_file "aoa-memo router semantic recall contract" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/examples/recall/recall_contract.router.semantic.json"
  check_warn_file "aoa-memo router lineage recall contract" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/examples/recall/recall_contract.router.lineage.json"
  check_warn_file "aoa-memo object working recall contract" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/examples/recall/recall_contract.object.working.json"
  check_warn_file "aoa-memo object semantic recall contract" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/examples/recall/recall_contract.object.semantic.json"
  check_warn_file "aoa-memo object lineage recall contract" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/examples/recall/recall_contract.object.lineage.json"
  check_warn_file "aoa-memo object return-ready recall contract" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/examples/recall/recall_contract.object.working.return.json"
  check_warn_file "aoa-memo checkpoint schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/mechanics/checkpoint/parts/checkpoint-to-memory-mapping/schemas/checkpoint-to-memory-contract.schema.json"
  check_warn_file "aoa-memo core contract schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo/schemas/support-objects/core-memory-contract.schema.json"
  check_warn_file "aoa-evals docs map" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/docs/README.md"
  check_warn_file "aoa-evals trace bridge doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/docs/TRACE_EVAL_BRIDGE.md"
  check_warn_file "aoa-evals runtime bench promotion doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/docs/RUNTIME_BENCH_PROMOTION_GUIDE.md"
  check_warn_file "aoa-evals self-agent checkpoint posture doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/docs/SELF_AGENT_CHECKPOINT_EVAL_POSTURE.md"
  check_warn_file "aoa-evals recurrence proof program doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/docs/RECURRENCE_PROOF_PROGRAM.md"
  check_warn_file "aoa-evals catalog" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/eval_catalog.min.json"
  check_warn_file "aoa-evals capsules" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/eval_capsules.json"
  check_warn_file "aoa-evals sections" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/eval_sections.full.json"
  check_warn_file "aoa-evals comparison spine" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/comparison_spine.json"
  check_warn_file "aoa-evals report index" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/eval_report_index.min.json"
  check_file "aoa-evals runtime candidate template index" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/runtime_candidate_template_index.min.json"
  check_file "aoa-evals runtime candidate intake" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/generated/runtime_candidate_intake.min.json"
  check_file "aoa-evals workhorse evidence template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/examples/runtime_evidence_selection.workhorse-local.example.json"
  check_file "aoa-evals return evidence template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/examples/runtime_evidence_selection.return-anchor-integrity.example.json"
  check_file "aoa-evals memo recall evidence template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/${AOA_EVALS_MEMO_RECALL_UPSTREAM_TEMPLATE}"
  check_file "aoa-evals memo contradiction gap evidence template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/${AOA_EVALS_MEMO_CONTRADICTION_GAP_UPSTREAM_TEMPLATE}"
  check_file "aoa-evals memo contradiction rerun evidence template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/${AOA_EVALS_MEMO_CONTRADICTION_RERUN_UPSTREAM_TEMPLATE}"
  check_warn_file "aoa-evals self-agent hook template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json"
  check_warn_file "aoa-evals model-tier hook template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/examples/artifact_to_verdict_hook.long-horizon-model-tier-orchestra.example.json"
  check_warn_file "aoa-evals restartable hook template" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/examples/artifact_to_verdict_hook.restartable-inquiry-loop.example.json"
  check_warn_file "aoa-evals runtime evidence schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/schemas/runtime-evidence-selection.schema.json"
  check_warn_file "aoa-evals artifact hook schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/schemas/artifact-to-verdict-hook.schema.json"
  check_file "aoa-playbooks registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_registry.min.json"
  check_file "aoa-playbooks activation" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_activation_surfaces.min.json"
  check_file "aoa-playbooks federation" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_federation_surfaces.min.json"
  check_file "aoa-playbooks review status" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_review_status.min.json"
  check_file "aoa-playbooks review packet contracts" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_review_packet_contracts.min.json"
  check_file "aoa-playbooks review intake" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_review_intake.min.json"
  check_file "aoa-playbooks handoffs" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_handoff_contracts.json"
  check_file "aoa-playbooks failures" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_failure_catalog.json"
  check_file "aoa-playbooks subagent recipes" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_subagent_recipes.json"
  check_file "aoa-playbooks automation plans" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/${AOA_PLAYBOOKS_AUTOMATION_PLANS_UPSTREAM_FILE}"
  check_file "aoa-playbooks composition manifest" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/generated/playbook_composition_manifest.json"
  check_file "aoa-playbooks registry schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks/schemas/playbook-registry.schema.json"
  check_warn_file "aoa-kag consumer guide" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/CONSUMER_GUIDE.md"
  check_warn_file "aoa-kag reasoning handoff doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/REASONING_HANDOFF.md"
  check_warn_file "aoa-kag reasoning handoff pack doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/REASONING_HANDOFF_PACK.md"
  check_warn_file "aoa-kag recurrence regrounding doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/RECURRENCE_REGROUNDING.md"
  check_warn_file "aoa-kag bridge contracts doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/BRIDGE_CONTRACTS.md"
  check_warn_file "aoa-kag readiness doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/FEDERATION_KAG_READINESS.md"
  check_warn_file "aoa-kag counterpart contract doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/COUNTERPART_CONSUMER_CONTRACT.md"
  check_warn_file "aoa-kag ToS axis doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/TOS_RETRIEVAL_AXIS_PACK.md"
  check_warn_file "aoa-kag Zarathustra retrieval doc" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/docs/TOS_ZARATHUSTRA_ROUTE_RETRIEVAL_PACK.md"
  check_warn_file "aoa-kag registry" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/kag_registry.min.json"
  check_warn_file "aoa-kag federation spine" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/federation_spine.min.json"
  check_warn_file "aoa-kag tiny consumer bundle" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/tiny_consumer_bundle.min.json"
  check_warn_file "aoa-kag reasoning handoff pack" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/reasoning_handoff_pack.min.json"
  check_warn_file "aoa-kag return regrounding pack" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/return_regrounding_pack.min.json"
  check_warn_file "aoa-kag technique lift pack" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/technique_lift_pack.min.json"
  check_warn_file "aoa-kag ToS retrieval axis pack" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/tos_retrieval_axis_pack.min.json"
  check_warn_file "aoa-kag ToS text chunk map" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/tos_text_chunk_map.min.json"
  check_warn_file "aoa-kag cross-source projection" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/cross_source_node_projection.min.json"
  check_warn_file "aoa-kag counterpart exposure review" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/counterpart_federation_exposure_review.min.json"
  check_warn_file "aoa-kag Zarathustra retrieval pack" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/generated/tos_zarathustra_route_retrieval_pack.min.json"
  check_warn_file "aoa-kag registry schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/kag-registry.schema.json"
  check_warn_file "aoa-kag federation spine schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/federation-spine.schema.json"
  check_warn_file "aoa-kag tiny consumer schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/tiny-consumer-bundle.schema.json"
  check_warn_file "aoa-kag reasoning handoff schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/reasoning-handoff-pack.schema.json"
  check_warn_file "aoa-kag regrounding schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/return-regrounding-pack.schema.json"
  check_warn_file "aoa-kag technique lift schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/technique-lift-pack.schema.json"
  check_warn_file "aoa-kag ToS axis schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/tos-retrieval-axis-pack.schema.json"
  check_warn_file "aoa-kag ToS chunk map schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/tos-text-chunk-map.schema.json"
  check_warn_file "aoa-kag cross-source projection schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/cross-source-node-projection.schema.json"
  check_warn_file "aoa-kag counterpart exposure schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/counterpart-federation-exposure-review.schema.json"
  check_warn_file "aoa-kag Zarathustra retrieval schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/tos-zarathustra-route-retrieval-pack.schema.json"
  check_warn_file "aoa-kag counterpart consumer contract schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/counterpart-consumer-contract.schema.json"
  check_warn_file "aoa-kag bridge envelope schema" "${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag/schemas/bridge-envelope.schema.json"
  check_warn_file "tos-source KAG export doc" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/docs/KAG_EXPORT.md"
  check_warn_file "tos-source tiny entry route doc" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/docs/TINY_ENTRY_ROUTE.md"
  check_warn_file "tos-source node contract doc" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/docs/NODE_CONTRACT.md"
  check_warn_file "tos-source practice branch doc" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/docs/PRACTICE_BRANCH.md"
  check_warn_file "tos-source Zarathustra entry doc" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/docs/ZARATHUSTRA_TRILINGUAL_ENTRY.md"
  check_warn_file "tos-source KAG export" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/generated/kag_export.min.json"
  check_warn_file "tos-source entry example" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/examples/source_node.example.json"
  check_warn_file "tos-source tiny entry route example" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/examples/tos_tiny_entry_route.example.json"
  check_warn_file "tos-source node contract schema" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/schemas/tos-node-contract.schema.json"
  check_warn_file "tos-source tiny entry route schema" "${AOA_STACK_ROOT}/Knowledge/federation/tos-source/schemas/tos-tiny-entry-route.schema.json"
fi

if ((selection_metadata_ready)) && has_module "52-tos-graph.yml"; then
  aoa_note "selected runtime includes 52-tos-graph.yml; checking preview-first ToS graph helper surfaces"
  check_dir "${AOA_STACK_ROOT}/Logs/tos-graph"
  check_warn_file "tos-graph env" "${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env"
  check_warn_file "tos-graph config" "${AOA_STACK_ROOT}/Configs/tos-graph/config.yaml"
  check_warn_file "tos-graph Dockerfile" "${AOA_STACK_ROOT}/Services/tos-graph/Dockerfile"
  check_warn_file "tos-graph main app" "${AOA_STACK_ROOT}/Services/tos-graph/app/main.py"
fi

if ((errors > 0)); then
  aoa_die "layout check failed with ${errors} hard errors"
fi

if ((strict_mode)) && ((warnings > 0)); then
  aoa_die "layout check found ${warnings} warnings in strict mode"
fi

aoa_note "layout check passed"
if ((warnings > 0)); then
  aoa_note "warnings: ${warnings}"
fi
