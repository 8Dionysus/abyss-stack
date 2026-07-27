#!/usr/bin/env bash
set -euo pipefail

stack_root="${AOA_STACK_ROOT:-/srv/AbyssOS/abyss-stack}"
legacy_credential_path="${AOA_MCP_HTTP_CREDENTIAL_FILE:-${stack_root}/Secrets/Configs/aoa-mcp-http-bearer-token}"

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

load_credential \
  "$legacy_credential_path" \
  "AOA_MCP_HTTP_BEARER_TOKEN" \
  "legacy MCP HTTP bearer credential"
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
  "${stack_root}/Secrets/Configs/aoa-course-connector-mcp-read-bearer-token" \
  "AOA_COURSE_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-course-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-discord-connector-mcp-read-bearer-token" \
  "AOA_DISCORD_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-discord-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-session-memory-mcp-read-bearer-token" \
  "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN" \
  "aoa-session-memory MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-stackoverflow-connector-mcp-read-bearer-token" \
  "AOA_STACKOVERFLOW_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-stackoverflow-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-stats-mcp-read-bearer-token" \
  "AOA_STATS_MCP_READ_BEARER_TOKEN" \
  "aoa-stats MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-telegram-connector-mcp-read-bearer-token" \
  "AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-telegram-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-xda-connector-mcp-read-bearer-token" \
  "AOA_XDA_CONNECTOR_MCP_READ_BEARER_TOKEN" \
  "aoa-xda-connector MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/abyss-machine-mcp-read-bearer-token" \
  "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN" \
  "abyss-machine MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/tos-corpus-mcp-read-bearer-token" \
  "TOS_CORPUS_MCP_READ_BEARER_TOKEN" \
  "tos-corpus MCP read bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-memo-mcp-candidate-bearer-token" \
  "AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN" \
  "aoa-memo MCP candidate bearer credential"
load_credential \
  "${stack_root}/Secrets/Configs/aoa-evals-mcp-candidate-bearer-token" \
  "AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN" \
  "aoa-evals MCP candidate bearer credential"

codex_executable="${AOA_CODEX_EXECUTABLE:-}"
if [[ -z "$codex_executable" ]]; then
  codex_executable="$(command -v codex || true)"
fi
[[ -n "$codex_executable" && -x "$codex_executable" && ! -d "$codex_executable" ]] || \
  fail "Codex executable was not found"

launcher_real="$(readlink -f "$0")"
codex_real="$(readlink -f "$codex_executable")"
[[ "$launcher_real" != "$codex_real" ]] || fail "Codex executable resolves back to this launcher"

unset AOA_MCP_HTTP_CREDENTIAL_FILE AOA_CODEX_EXECUTABLE
exec "$codex_executable" "$@"
