#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

aoa_note "creating runtime layout under ${AOA_STACK_ROOT}"

mkdir -p \
  "${AOA_STACK_ROOT}/Configs" \
  "${AOA_STACK_ROOT}/Configs/agent-api" \
  "${AOA_STACK_ROOT}/Configs/federation" \
  "${AOA_STACK_ROOT}/Configs/monitoring/alloy" \
  "${AOA_STACK_ROOT}/Configs/monitoring/alertmanager" \
  "${AOA_STACK_ROOT}/Configs/monitoring/grafana/provisioning/datasources" \
  "${AOA_STACK_ROOT}/Configs/monitoring/grafana/provisioning/dashboards" \
  "${AOA_STACK_ROOT}/Configs/monitoring/loki" \
  "${AOA_STACK_ROOT}/Configs/monitoring/tempo" \
  "${AOA_STACK_ROOT}/Configs/tts" \
  "${AOA_STACK_ROOT}/Configs/ollama" \
  "${AOA_STACK_ROOT}/Configs/tos-graph" \
  "${AOA_STACK_ROOT}/Secrets/Configs" \
  "${AOA_STACK_ROOT}/Services" \
  "${AOA_STACK_ROOT}/Services/n8n" \
  "${AOA_STACK_ROOT}/Services/litellm" \
  "${AOA_STACK_ROOT}/Services/aoa-browser/ms-playwright" \
  "${AOA_STACK_ROOT}/Services/monitoring/prometheus" \
  "${AOA_STACK_ROOT}/Services/monitoring/alertmanager" \
  "${AOA_STACK_ROOT}/Services/monitoring/loki" \
  "${AOA_STACK_ROOT}/Services/monitoring/tempo" \
  "${AOA_STACK_ROOT}/Services/monitoring/alloy" \
  "${AOA_STACK_ROOT}/Services/monitoring/grafana" \
  "${AOA_STACK_ROOT}/Models" \
  "${AOA_STACK_ROOT}/Knowledge" \
  "${AOA_STACK_ROOT}/Knowledge/federation" \
  "${AOA_STACK_ROOT}/Knowledge/n8n-docs" \
  "${AOA_STACK_ROOT}/Logs" \
  "${AOA_STACK_ROOT}/Logs/machine-bridge/latest" \
  "${AOA_STACK_ROOT}/Logs/machine-bridge/records" \
  "${AOA_STACK_ROOT}/Logs/eval-exports/latest/runtime-evidence-selection" \
  "${AOA_STACK_ROOT}/Logs/eval-exports/latest/artifact-hook" \
  "${AOA_STACK_ROOT}/Logs/eval-exports/records" \
  "${AOA_STACK_ROOT}/Logs/diagnostics/latest" \
  "${AOA_STACK_ROOT}/Logs/diagnostics/records" \
  "${AOA_STACK_ROOT}/Logs/governed-runs" \
  "${AOA_STACK_ROOT}/Logs/langgraph-inventory" \
  "${AOA_STACK_ROOT}/Logs/memo-exports/latest" \
  "${AOA_STACK_ROOT}/Logs/memo-exports/records" \
  "${AOA_STACK_ROOT}/Logs/rpg/latest" \
  "${AOA_STACK_ROOT}/Logs/rpg/records" \
  "${AOA_STACK_ROOT}/Logs/tos-graph" \
  "${AOA_STACK_ROOT}/Logs/returns" \
  "${AOA_STACK_ROOT}/Logs/tts" \
  "${AOA_STACK_ROOT}/.codex-home"

aoa_note "layout ready"
aoa_note "no destructive changes were made"
