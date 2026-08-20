#!/usr/bin/env bash
set -euo pipefail

stack_root="${AOA_STACK_ROOT:-/srv/AbyssOS/abyss-stack}"
modern_codex_default="/srv/abyss-machine/runtimes/codex-os-abyss-mcp/0.147.0-abyss.2/bin/codex-os-abyss-mcp"
modern_server_default="abyss_stack,abyss_machine,aoa_decisions,aoa_memo,aoa_session_memory,aoa_evals,aoa_kag,aoa_stats,aoa_4pda_connector,aoa_telegram_connector,aoa_discord_connector"
readiness_service="abyss-mcp-modern-admission-refresh.service"

readiness_units=(
  abyss-stack-mcp-read.service
  aoa-organ-mcp-read@abyss-machine.service
  aoa-organ-mcp-read@aoa-decisions.service
  aoa-organ-mcp-read@aoa-memo.service
  aoa-organ-mcp-read@aoa-session-memory.service
  aoa-organ-mcp-read@aoa-evals.service
  aoa-organ-mcp-read@aoa-kag.service
  aoa-organ-mcp-read@aoa-stats.service
  aoa-organ-mcp-read@aoa-4pda-connector.service
  aoa-organ-mcp-read@aoa-telegram-connector.service
  aoa-organ-mcp-read@aoa-discord-connector.service
)
readiness_ports=(5420 5421 5422 5423 5424 5425 5426 5427 5428 5430 5431)

fail() {
  printf 'abyss-stack Codex MCP HTTP client: %s\n' "$1" >&2
  exit 78
}

load_credential() {
  local credential_path="$1"
  local environment_name="$2"
  local label="$3"
  local credential_mode=""
  local credential_owner=""
  local token=""
  local token_size=0
  local credential_size=0
  local existing_token="${!environment_name:-}"

  [[ -f "$credential_path" && ! -L "$credential_path" && -r "$credential_path" ]] || \
    fail "${label} must be a readable regular non-symlink file"

  credential_mode="$(stat -c '%a' "$credential_path")"
  credential_owner="$(stat -c '%u' "$credential_path")"
  [[ "$credential_mode" == "600" ]] || fail "${label} must have mode 0600"
  [[ "$credential_owner" == "$(id -u)" ]] || \
    fail "${label} must be owned by the current user"

  token="$(<"$credential_path")"
  token_size="${#token}"
  credential_size="$(stat -c '%s' "$credential_path")"
  if [[ ! "$token" =~ ^[A-Za-z0-9._~-]{43,512}$ ]] || \
    ! ((credential_size == token_size || credential_size == token_size + 1)); then
    fail "${label} has invalid content"
  fi

  if [[ -n "$existing_token" && "$existing_token" != "$token" ]]; then
    fail "existing ${environment_name} conflicts with the deployed credential"
  fi

  printf -v "$environment_name" '%s' "$token"
  # shellcheck disable=SC2163  # environment_name intentionally names the export.
  export "$environment_name"
}

metadata_only_invocation() {
  local arg=""
  local expect_option_value=0
  local first_positional=""

  for arg in "$@"; do
    case "$arg" in
      --)
        break
        ;;
      -h|--help|-V|--version)
        return 0
        ;;
    esac
  done

  for arg in "$@"; do
    if [[ "$expect_option_value" -eq 1 ]]; then
      expect_option_value=0
      continue
    fi
    case "$arg" in
      -c|--config|--enable|--disable|--remote|--remote-auth-token-env|\
      -i|--image|-m|--model|--local-provider|-p|--profile|-s|--sandbox|\
      -C|--cd|--add-dir|-a|--ask-for-approval)
        expect_option_value=1
        ;;
      --)
        break
        ;;
      -*)
        ;;
      *)
        first_positional="$arg"
        break
        ;;
    esac
  done

  case "$first_positional" in
    completion|features|help|login|logout|mcp|plugin)
      return 0
      ;;
  esac
  return 1
}

modern_fleet_ready() {
  local active_units=0
  local listening_ports=0

  read -r active_units listening_ports < <(modern_fleet_counts)
  ((active_units == ${#readiness_units[@]})) && \
    ((listening_ports == ${#readiness_ports[@]}))
}

modern_fleet_counts() {
  local active_units=0
  local listening_ports=0
  local listeners=""
  local port=""
  local unit=""

  if ! command -v systemctl >/dev/null 2>&1 || ! command -v ss >/dev/null 2>&1; then
    printf '0 0\n'
    return 0
  fi
  for unit in "${readiness_units[@]}"; do
    if systemctl --user is-active --quiet "$unit"; then
      ((active_units += 1))
    fi
  done
  listeners="$(ss -H -ltn 2>/dev/null || true)"
  for port in "${readiness_ports[@]}"; do
    if grep -Eq "(^|[[:space:]])127\\.0\\.0\\.1:${port}([[:space:]]|$)" <<<"$listeners"; then
      ((listening_ports += 1))
    fi
  done
  printf '%s %s\n' "$active_units" "$listening_ports"
}

request_modern_fleet_recovery() {
  local skip="${AOA_MCP_READINESS_SKIP:-0}"

  case "${skip,,}" in
    1|true|yes|on)
      return 0
      ;;
  esac
  metadata_only_invocation "$@" && return 0
  modern_fleet_ready && return 0

  if command -v systemctl >/dev/null 2>&1 && \
     systemctl --user start --no-block "$readiness_service"; then
    printf '%s\n' \
      "OS Abyss MCP: read fleet is unavailable; background recovery requested. Starting Codex without blocking." \
      >&2
  else
    printf '%s\n' \
      "OS Abyss MCP: read fleet is unavailable and background recovery could not be requested. Starting Codex without MCP readiness." \
      >&2
  fi
}

load_credential \
  "${stack_root}/Secrets/Configs/aoa-decisions-mcp-read-bearer-token" \
  "AOA_DECISIONS_MCP_READ_BEARER_TOKEN" \
  "aoa-decisions MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-memo-mcp-read-bearer-token" \
  "AOA_MEMO_MCP_READ_BEARER_TOKEN" \
  "aoa-memo MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-evals-mcp-read-bearer-token" \
  "AOA_EVALS_MCP_READ_BEARER_TOKEN" \
  "aoa-evals MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-kag-mcp-read-bearer-token" \
  "AOA_KAG_MCP_READ_BEARER_TOKEN" \
  "aoa-kag MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-4pda-connector-mcp-read-bearer-token" \
  "AOA_4PDA_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-4pda-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-discord-connector-mcp-read-bearer-token" \
  "AOA_DISCORD_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-discord-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-session-memory-mcp-read-bearer-token" \
  "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN" \
  "aoa-session-memory MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-stats-mcp-read-bearer-token" \
  "AOA_STATS_MCP_READ_BEARER_TOKEN" \
  "aoa-stats MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-telegram-connector-mcp-read-bearer-token" \
  "AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-telegram-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/abyss-machine-mcp-read-bearer-token" \
  "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN" \
  "abyss-machine MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/abyss-stack-mcp-read-bearer-token" \
  "ABYSS_STACK_MCP_READ_BEARER_TOKEN" \
  "abyss-stack MCP read bearer credential"

codex_executable="${AOA_CODEX_EXECUTABLE:-}"
if [[ -z "$codex_executable" ]]; then
  if [[ -x "$modern_codex_default" && ! -d "$modern_codex_default" ]]; then
    codex_executable="$modern_codex_default"
  else
    codex_executable="$(command -v codex || true)"
  fi
fi
[[ -n "$codex_executable" && -x "$codex_executable" && ! -d "$codex_executable" ]] || \
  fail "Codex executable was not found"

launcher_real="$(readlink -f "$0")"
codex_real="$(readlink -f "$codex_executable")"
[[ "$launcher_real" != "$codex_real" ]] || fail "Codex executable resolves back to this launcher"

if [[ "$codex_real" == "$(readlink -f "$modern_codex_default")" ]]; then
  export CODEX_MCP_2026_SERVERS="${CODEX_MCP_2026_SERVERS:-$modern_server_default}"
fi

request_modern_fleet_recovery "$@"

unset AOA_CODEX_EXECUTABLE
unset AOA_MCP_READINESS_SKIP
exec "$codex_executable" "$@"
