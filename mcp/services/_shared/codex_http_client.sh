#!/usr/bin/env bash
set -euo pipefail

stack_root="${AOA_STACK_ROOT:-}"
managed_codex_default="${HOME}/.codex/packages/standalone/current/bin/codex"
launcher_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
runtime_catalog_script="${ABYSS_MCP_RUNTIME_CATALOG:-${launcher_dir}/../../protocol-lab/scripts/runtime_catalog.py}"
runtime_config="${ABYSS_MCP_RUNTIME_CONFIG:-${launcher_dir}/runtime-config.v1.json}"
client_mode="${AOA_CODEX_CLIENT_MODE:-codex}"
codex_mcp_feature=""
readiness_service=""
credentials_root=""
readiness_units=()
readiness_ports=()
readiness_credentials=()
readiness_environment_names=()

fail() {
  printf 'abyss-stack Codex MCP HTTP client: %s\n' "$1" >&2
  exit 78
}

load_runtime_catalog() {
  local -a catalog_args=(
    "$runtime_catalog_script"
    --runtime-config "$runtime_config"
    --emit codex-client
  )
  [[ -n "$stack_root" ]] && catalog_args+=(--stack-root "$stack_root")
  command -v python3 >/dev/null 2>&1 || fail "python3 is required to read the MCP runtime catalog"
  local projection=""
  projection="$(python3 "${catalog_args[@]}")" || \
    fail "MCP runtime catalog could not produce the Codex client projection"

  local kind first second third fourth
  while IFS=$'\t' read -r kind first second third fourth; do
    case "$kind" in
      FEATURE)
        [[ -z "$codex_mcp_feature" ]] || fail "MCP runtime catalog emitted duplicate Codex feature"
        codex_mcp_feature="$first"
        ;;
      RECOVERY)
        [[ -z "$readiness_service" ]] || fail "MCP runtime catalog emitted duplicate recovery unit"
        readiness_service="$first"
        ;;
      STACK_ROOT)
        [[ -z "$stack_root" ]] || continue
        stack_root="$first"
        ;;
      CREDENTIALS_ROOT)
        [[ -z "$credentials_root" ]] || fail "MCP runtime catalog emitted duplicate credentials root"
        credentials_root="$first"
        ;;
      READ)
        [[ -n "$first" && -n "$second" && -n "$third" && -n "$fourth" ]] || \
          fail "MCP runtime catalog emitted an incomplete read contour"
        readiness_units+=("$first")
        readiness_ports+=("$second")
        readiness_credentials+=("$third")
        readiness_environment_names+=("$fourth")
        ;;
      "")
        ;;
      *)
        fail "MCP runtime catalog emitted an unknown record: $kind"
        ;;
    esac
  done <<< "$projection"

  [[ -n "$stack_root" && -n "$credentials_root" && -n "$codex_mcp_feature" && -n "$readiness_service" ]] || \
    fail "MCP runtime catalog omitted required Codex client settings"
  ((${#readiness_units[@]} > 0)) || fail "MCP runtime catalog contains no client read contours"
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
    if awk -v suffix=":${port}" \
      'index($4, suffix) == length($4) - length(suffix) + 1 { found = 1 }
       END { exit(found ? 0 : 1) }' <<<"$listeners"; then
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

load_runtime_catalog

case "$client_mode" in
  codex|desktop)
    ;;
  *)
    fail "AOA_CODEX_CLIENT_MODE must be codex or desktop"
    ;;
esac

for index in "${!readiness_credentials[@]}"; do
  load_credential \
    "${credentials_root}/${readiness_credentials[$index]}" \
    "${readiness_environment_names[$index]}" \
    "MCP read bearer credential ${readiness_credentials[$index]}"
done

codex_executable="${AOA_CODEX_EXECUTABLE:-}"
if [[ -z "$codex_executable" ]]; then
  if [[ "$client_mode" == "desktop" ]]; then
    codex_executable="/usr/bin/chatgpt"
  elif [[ -x "$managed_codex_default" && ! -d "$managed_codex_default" ]]; then
    codex_executable="$managed_codex_default"
  else
    codex_executable="$(command -v codex || true)"
  fi
fi
[[ -n "$codex_executable" && -x "$codex_executable" && ! -d "$codex_executable" ]] || \
  fail "Codex executable was not found"

launcher_real="$(readlink -f "$0")"
codex_real="$(readlink -f "$codex_executable")"
[[ "$launcher_real" != "$codex_real" ]] || fail "Codex executable resolves back to this launcher"

request_modern_fleet_recovery "$@"

unset AOA_CODEX_EXECUTABLE
unset AOA_CODEX_CLIENT_MODE
unset AOA_MCP_READINESS_SKIP
if [[ "$client_mode" == "desktop" ]]; then
  exec "$codex_executable" "$@"
fi
exec "$codex_executable" --enable "$codex_mcp_feature" "$@"
