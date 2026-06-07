#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

with_internal=0
internal_strict=0
selector_args=()
while (($#)); do
  case "$1" in
    --with-internal)
      with_internal=1
      ;;
    --with-internal-strict)
      with_internal=1
      internal_strict=1
      ;;
    *)
      selector_args+=("$1")
      ;;
  esac
  shift || true
done

aoa_parse_profile_args "${selector_args[@]}"
aoa_resolve_modules
aoa_print_profile_summary

failures=0
has_module() {
  local target="$1"
  local module
  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

if has_module "10-storage.yml"; then
  aoa_probe_tcp "postgres" "127.0.0.1" "5432" || failures=$((failures + 1))
  aoa_probe_tcp "redis" "127.0.0.1" "6379" || failures=$((failures + 1))
  aoa_probe_http "qdrant" "http://127.0.0.1:6333/" || failures=$((failures + 1))
  aoa_probe_http "neo4j" "http://127.0.0.1:7474/" || failures=$((failures + 1))
fi

if has_module "20-orchestration.yml"; then
  aoa_probe_http "n8n" "http://127.0.0.1:5678/" || failures=$((failures + 1))
fi

if has_module "30-local-inference.yml"; then
  aoa_probe_http "ollama" "http://127.0.0.1:11434/api/tags" || failures=$((failures + 1))
fi

if has_module "32-llamacpp-inference.yml"; then
  aoa_probe_http "llama-cpp" "http://127.0.0.1:11435/health" || failures=$((failures + 1))
fi

if has_module "31-intel-inference.yml"; then
  aoa_probe_http "ovms" "http://127.0.0.1:8200/v2/health/live" || failures=$((failures + 1))
fi

if has_module "40-llm-gateway.yml"; then
  aoa_probe_tcp "litellm" "127.0.0.1" "4000" || failures=$((failures + 1))
fi

if has_module "41-agent-api.yml"; then
  aoa_probe_http "langchain-api" "http://127.0.0.1:5403/health" || failures=$((failures + 1))
  "${SCRIPTS_DIR}/aoa-qwen-check" --case exact-reply --url "http://127.0.0.1:5403/run" || failures=$((failures + 1))
fi

if has_module "44-llamacpp-agent-sidecar.yml"; then
  aoa_probe_http "langchain-api-llamacpp" "http://127.0.0.1:5403/health" || failures=$((failures + 1))
  "${SCRIPTS_DIR}/aoa-qwen-check" --case exact-reply || failures=$((failures + 1))
fi

if has_module "43-federation-router.yml"; then
  aoa_probe_http "route-api" "http://127.0.0.1:5402/health" || failures=$((failures + 1))
  aoa_probe_http "route-api memo" "http://127.0.0.1:5402/memo/registry" || failures=$((failures + 1))
  aoa_probe_http "route-api evals" "http://127.0.0.1:5402/evals/catalog" || failures=$((failures + 1))
  aoa_probe_http "route-api playbooks" "http://127.0.0.1:5402/playbooks/activation" || failures=$((failures + 1))
  aoa_probe_http "route-api kag" "http://127.0.0.1:5402/kag/registry" || failures=$((failures + 1))
  aoa_probe_http "route-api tos" "http://127.0.0.1:5402/kag/tos-export" || failures=$((failures + 1))
fi

if has_module "43-federation-router.yml" && { has_module "41-agent-api.yml" || has_module "44-llamacpp-agent-sidecar.yml"; }; then
  "${SCRIPTS_DIR}/aoa-federated-check" || failures=$((failures + 1))
fi

if has_module "45-rerank-api.yml"; then
  aoa_probe_http "rerank-api" "http://127.0.0.1:${AOA_RERANK_HOST_PORT:-5405}/health" || failures=$((failures + 1))
fi

if has_module "46-rag-api.yml"; then
  aoa_probe_http "rag-api" "http://127.0.0.1:${AOA_RAG_API_HOST_PORT:-5406}/health" || failures=$((failures + 1))
  aoa_probe_http "rag-api sources" "http://127.0.0.1:${AOA_RAG_API_HOST_PORT:-5406}/sources" || failures=$((failures + 1))
  aoa_probe_http "rag-api dag" "http://127.0.0.1:${AOA_RAG_API_HOST_PORT:-5406}/dag/jobs" || failures=$((failures + 1))
fi

if has_module "52-tos-graph.yml"; then
  aoa_probe_http "tos-graph" "http://127.0.0.1:5410/health" || failures=$((failures + 1))
fi

if has_module "53-babelvox-tts.yml"; then
  aoa_probe_http "babelvox-tts" "http://127.0.0.1:${AOA_BABELVOX_TTS_HOST_PORT:-5102}/health" || failures=$((failures + 1))
fi

if has_module "50-speech.yml"; then
  aoa_probe_http "qwen-tts" "http://127.0.0.1:5101/health" || failures=$((failures + 1))
  aoa_probe_http "tts-router" "http://127.0.0.1:5201/health" || failures=$((failures + 1))
fi

if has_module "51-browser-tools.yml"; then
  if ((with_internal)); then
    aoa_note "browser-tools internal probes requested"
  else
    aoa_note "skip browser-tools host probes because docs-api and aoa-browser are internal-only"
  fi
fi

if has_module "60-monitoring.yml"; then
  aoa_probe_http "prometheus" "http://127.0.0.1:9090/-/ready" || failures=$((failures + 1))
  aoa_probe_http "alertmanager" "http://127.0.0.1:9093/-/ready" || failures=$((failures + 1))
  aoa_probe_http "grafana" "http://127.0.0.1:3000/api/health" || failures=$((failures + 1))
  if ((with_internal)); then
    aoa_note "monitoring internal probes requested"
  else
    aoa_note "skip cadvisor, loki, and alloy host probes because they are internal-only"
  fi
fi

if ((with_internal)); then
  internal_args=()
  if ((internal_strict)); then
    internal_args+=(--strict)
  fi
  AOA_STACK_PRESET="$AOA_STACK_PRESET" AOA_STACK_PROFILE="$AOA_STACK_PROFILE" "${SCRIPTS_DIR}/aoa-internal-probes" "${internal_args[@]}" || failures=$((failures + 1))
fi

if ((failures > 0)); then
  aoa_die "smoke checks failed: ${failures}"
fi

aoa_note "smoke checks passed"
