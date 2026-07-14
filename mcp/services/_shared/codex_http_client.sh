#!/usr/bin/env bash
set -euo pipefail

credential_path="${AOA_MCP_HTTP_CREDENTIAL_FILE:-${AOA_STACK_ROOT:-/srv/AbyssOS/abyss-stack}/Secrets/Configs/aoa-mcp-http-bearer-token}"

fail() {
  printf 'abyss-stack Codex MCP HTTP client: %s\n' "$1" >&2
  exit 78
}

[[ -f "$credential_path" && ! -L "$credential_path" && -r "$credential_path" ]] || \
  fail "bearer credential must be a readable regular non-symlink file"

credential_mode="$(stat -c '%a' "$credential_path")"
credential_owner="$(stat -c '%u' "$credential_path")"
[[ "$credential_mode" == "600" ]] || fail "bearer credential must have mode 0600"
[[ "$credential_owner" == "$(id -u)" ]] || fail "bearer credential must be owned by the current user"

token="$(<"$credential_path")"
token_size="${#token}"
credential_size="$(stat -c '%s' "$credential_path")"
if [[ ! "$token" =~ ^[A-Za-z0-9._~-]{43,512}$ ]] || \
  ! ((credential_size == token_size || credential_size == token_size + 1)); then
  fail "bearer credential has invalid content"
fi

if [[ -n "${AOA_MCP_HTTP_BEARER_TOKEN:-}" && "$AOA_MCP_HTTP_BEARER_TOKEN" != "$token" ]]; then
  fail "existing bearer environment conflicts with the deployed credential"
fi

codex_executable="${AOA_CODEX_EXECUTABLE:-}"
if [[ -z "$codex_executable" ]]; then
  codex_executable="$(command -v codex || true)"
fi
[[ -n "$codex_executable" && -x "$codex_executable" && ! -d "$codex_executable" ]] || \
  fail "Codex executable was not found"

launcher_real="$(readlink -f "$0")"
codex_real="$(readlink -f "$codex_executable")"
[[ "$launcher_real" != "$codex_real" ]] || fail "Codex executable resolves back to this launcher"

export AOA_MCP_HTTP_BEARER_TOKEN="$token"
unset token AOA_MCP_HTTP_CREDENTIAL_FILE AOA_CODEX_EXECUTABLE
exec "$codex_executable" "$@"
