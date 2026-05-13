#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

aoa_parse_profile_args "$@"
aoa_resolve_modules
aoa_print_profile_summary

aoa_note ""
aoa_note "expected host-facing endpoints:"

has_module() {
  local target="$1"
  local module
  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

if has_module "10-storage.yml"; then
  aoa_note "- postgres         127.0.0.1:5432"
  aoa_note "- redis            127.0.0.1:6379"
  aoa_note "- qdrant           http://127.0.0.1:6333/"
  aoa_note "- neo4j            http://127.0.0.1:7474/"
fi

if has_module "20-orchestration.yml"; then
  aoa_note "- n8n              http://127.0.0.1:5678/"
fi

if has_module "30-local-inference.yml"; then
  aoa_note "- ollama           http://127.0.0.1:11434/api/tags"
fi

if has_module "32-llamacpp-inference.yml"; then
  aoa_note "- llama-cpp        http://127.0.0.1:11435/health"
fi

if has_module "31-intel-inference.yml"; then
  aoa_note "- ovms rest        http://127.0.0.1:8200/v2/health/live"
  aoa_note "- ovms grpc        127.0.0.1:9200"
fi

if has_module "40-llm-gateway.yml"; then
  aoa_note "- litellm          127.0.0.1:4000"
fi

if has_module "41-agent-api.yml"; then
  aoa_note "- langchain-api    http://127.0.0.1:5403/health"
fi

if has_module "44-llamacpp-agent-sidecar.yml"; then
  aoa_note "- langchain-api-llamacpp http://127.0.0.1:5403/health"
fi

if has_module "43-federation-router.yml"; then
  aoa_note "- route-api        http://127.0.0.1:5402/health"
  aoa_note "- route-api memo   http://127.0.0.1:5402/memo/registry"
  aoa_note "- route-api evals  http://127.0.0.1:5402/evals/catalog"
  aoa_note "- route-api plays  http://127.0.0.1:5402/playbooks/activation"
  aoa_note "- route-api kag    http://127.0.0.1:5402/kag/registry"
  aoa_note "- route-api tos    http://127.0.0.1:5402/kag/tos-export"
fi

if has_module "52-tos-graph.yml"; then
  aoa_note "- tos-graph        http://127.0.0.1:5410/health"
fi

if has_module "50-speech.yml"; then
  aoa_note "- qwen-tts         http://127.0.0.1:5101/health"
  aoa_note "- tts-router       http://127.0.0.1:5201/health"
fi

if has_module "60-monitoring.yml"; then
  aoa_note "- prometheus       http://127.0.0.1:9090/-/ready"
  aoa_note "- alertmanager     http://127.0.0.1:9093/-/ready"
  aoa_note "- grafana          http://127.0.0.1:3000/api/health"
fi

internal_notes=0
if has_module "51-browser-tools.yml"; then
  if ((internal_notes == 0)); then
    aoa_note ""
    aoa_note "internal-only notes:"
    internal_notes=1
  fi
  aoa_note "- docs-api is internal-only"
  aoa_note "- aoa-browser is internal-only"
fi

if has_module "60-monitoring.yml"; then
  if ((internal_notes == 0)); then
    aoa_note ""
    aoa_note "internal-only notes:"
    internal_notes=1
  fi
  aoa_note "- cadvisor is internal-only"
fi
