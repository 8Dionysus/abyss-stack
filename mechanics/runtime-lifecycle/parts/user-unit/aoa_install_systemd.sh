#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

enable_now=0
restart_now=0
link_all_user_units=0
link_system_units=0
provision_mcp_http_auth=0
provision_abyss_stack_mcp_auth=0
provision_abyss_stack_mcp_runtime=0
verify_abyss_stack_mcp_runtime=0
launch_verified_abyss_stack_mcp=0
install_mcp_http_codex_client=0
remove_mcp_http_codex_client=0
preset_spec=""
profile_spec=""
overlay_spec=""
value=""
selection_set=0
overlay_set=0

aoa_validate_runtime_spec() {
  local label="$1"
  local value="$2"

  [[ -n "$value" ]] || return 0
  if [[ ! "$value" =~ ^[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+)*$ ]]; then
    aoa_die "${label} must be a comma-separated list of profile or preset names"
  fi
}

aoa_append_runtime_spec() {
  local current="$1"
  local value="$2"

  if [[ -z "$current" ]]; then
    printf '%s\n' "$value"
  else
    printf '%s,%s\n' "$current" "$value"
  fi
}

aoa_validate_overlay_spec() {
  local value="$1"
  local raw_part trimmed resolved

  [[ -n "$value" ]] || return 0

  while IFS= read -r raw_part; do
    trimmed="$(aoa_trim "$raw_part")"
    [[ -n "$trimmed" ]] || aoa_die "overlay must not contain empty entries"
    if [[ ! "$trimmed" =~ ^[A-Za-z0-9_./-]+$ ]]; then
      aoa_die "overlay must be a comma-separated list of compose file paths"
    fi
    if [[ "$trimmed" == /* ]]; then
      resolved="$trimmed"
    else
      resolved="${AOA_CONFIGS_ROOT}/${trimmed}"
    fi
    [[ -f "$resolved" ]] || aoa_die "overlay compose file not found: $resolved"
  done < <(aoa_expand_specs "$value")
}

while (($#)); do
  case "$1" in
    --enable-now)
      enable_now=1
      ;;
    --restart-now)
      restart_now=1
      ;;
    --all-user-units)
      link_all_user_units=1
      ;;
    --system-units)
      link_system_units=1
      ;;
    --provision-mcp-http-auth)
      provision_mcp_http_auth=1
      ;;
    --provision-abyss-stack-mcp-auth)
      provision_abyss_stack_mcp_auth=1
      ;;
    --provision-abyss-stack-mcp-runtime)
      provision_abyss_stack_mcp_runtime=1
      ;;
    --verify-abyss-stack-mcp-runtime)
      verify_abyss_stack_mcp_runtime=1
      ;;
    --launch-verified-abyss-stack-mcp)
      launch_verified_abyss_stack_mcp=1
      ;;
    --install-mcp-http-codex-client)
      install_mcp_http_codex_client=1
      ;;
    --remove-mcp-http-codex-client)
      remove_mcp_http_codex_client=1
      ;;
    --preset)
      shift
      (($#)) || aoa_die "missing value after --preset"
      [[ -n "$1" ]] || aoa_die "preset must not be empty"
      preset_spec="$(aoa_append_runtime_spec "$preset_spec" "$1")"
      selection_set=1
      ;;
    --preset=*)
      value="${1#*=}"
      [[ -n "$value" ]] || aoa_die "preset must not be empty"
      preset_spec="$(aoa_append_runtime_spec "$preset_spec" "$value")"
      selection_set=1
      ;;
    --profile)
      shift
      (($#)) || aoa_die "missing value after --profile"
      [[ -n "$1" ]] || aoa_die "profile must not be empty"
      profile_spec="$(aoa_append_runtime_spec "$profile_spec" "$1")"
      selection_set=1
      ;;
    --profile=*)
      value="${1#*=}"
      [[ -n "$value" ]] || aoa_die "profile must not be empty"
      profile_spec="$(aoa_append_runtime_spec "$profile_spec" "$value")"
      selection_set=1
      ;;
    --overlay|--extra-compose-file|--extra-compose-files)
      option_name="$1"
      shift
      (($#)) || aoa_die "missing value after ${option_name}"
      overlay_spec="$(aoa_append_runtime_spec "$overlay_spec" "$1")"
      overlay_set=1
      ;;
    --overlay=*|--extra-compose-file=*|--extra-compose-files=*)
      overlay_spec="$(aoa_append_runtime_spec "$overlay_spec" "${1#*=}")"
      overlay_set=1
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

aoa_validate_runtime_spec "preset" "$preset_spec"
aoa_validate_runtime_spec "profile" "$profile_spec"
if ((overlay_set)) && [[ -z "$overlay_spec" ]]; then
  aoa_die "overlay must not be empty"
fi
if ((overlay_set && ! selection_set)); then
  aoa_die "--overlay requires --preset or --profile so the full runtime shape stays explicit"
fi
aoa_validate_overlay_spec "$overlay_spec"
if ((install_mcp_http_codex_client && remove_mcp_http_codex_client)); then
  aoa_die "cannot install and remove the MCP HTTP Codex client in one transaction"
fi
if ((provision_abyss_stack_mcp_runtime && link_all_user_units)); then
  aoa_die "link lock-aware user units in a separate transaction before abyss-stack MCP runtime provisioning"
fi
if ((verify_abyss_stack_mcp_runtime && \
      (provision_mcp_http_auth || provision_abyss_stack_mcp_auth || \
       provision_abyss_stack_mcp_runtime || install_mcp_http_codex_client || \
       remove_mcp_http_codex_client || enable_now || restart_now || \
       launch_verified_abyss_stack_mcp || link_all_user_units || \
       link_system_units || selection_set || overlay_set))); then
  aoa_die "abyss-stack MCP runtime verification must be a standalone read-only action"
fi
if ((launch_verified_abyss_stack_mcp && \
      (provision_mcp_http_auth || provision_abyss_stack_mcp_auth || \
       provision_abyss_stack_mcp_runtime || verify_abyss_stack_mcp_runtime || \
       install_mcp_http_codex_client || remove_mcp_http_codex_client || \
       enable_now || restart_now || link_all_user_units || link_system_units || \
       selection_set || overlay_set))); then
  aoa_die "verified abyss-stack MCP launch must be a standalone unit action"
fi
if (((install_mcp_http_codex_client || remove_mcp_http_codex_client) && EUID == 0)); then
  aoa_die "MCP HTTP Codex client install and removal must run as the target user, not root"
fi
if ((provision_abyss_stack_mcp_auth && EUID == 0)); then
  aoa_die "abyss-stack MCP credential provisioning must run as the target user, not root"
fi
if ((provision_abyss_stack_mcp_runtime && EUID == 0)); then
  aoa_die "abyss-stack MCP runtime provisioning must run as the target user, not root"
fi
if ((launch_verified_abyss_stack_mcp && EUID == 0)); then
  aoa_die "verified abyss-stack MCP launch must run as the target user, not root"
fi

mcp_http_credential_name="aoa-mcp-http-bearer-token"
mcp_http_secret_dir="${AOA_STACK_ROOT}/Secrets/Configs"
abyss_stack_mcp_read_credential_name="abyss-stack-mcp-read-bearer-token"
abyss_stack_mcp_candidate_credential_name="abyss-stack-mcp-candidate-bearer-token"
abyss_stack_mcp_service_root="${AOA_CONFIGS_ROOT}/mcp/services/abyss-stack-mcp"
abyss_stack_mcp_runtime_root="${AOA_STACK_ROOT}/Services/abyss-stack-mcp"
abyss_stack_mcp_venv="${abyss_stack_mcp_runtime_root}/venv"
abyss_stack_mcp_runtime_lock="${abyss_stack_mcp_runtime_root}/.runtime-provision.lock"
abyss_stack_mcp_source_lock_root="$(
  dirname -- "${AOA_CONFIGS_ROOT%/}"
)/Services/abyss-stack-mcp"
abyss_stack_mcp_source_lock="${abyss_stack_mcp_source_lock_root}/.source-projection.lock"
abyss_stack_mcp_bootstrap_python="${ABYSS_STACK_MCP_BOOTSTRAP_PYTHON:-/usr/bin/python3}"
abyss_stack_mcp_units_error=""
mcp_http_codex_launcher="${AOA_CONFIGS_ROOT}/mcp/services/_shared/codex_http_client.sh"
mcp_http_codex_zshrc="${ZDOTDIR:-${HOME}}/.zshrc"
mcp_http_codex_block_start="# >>> abyss-stack MCP HTTP Codex client >>>"
mcp_http_codex_block_end="# <<< abyss-stack MCP HTTP Codex client <<<"
mcp_http_codex_block_present=0

aoa_run_isolated_python() {
  local python_executable="$1"
  shift

  /usr/bin/env -u PYTHONHOME -u PYTHONPATH \
    "$python_executable" -I "$@"
}

aoa_validate_mcp_bearer_file() {
  local credential_path="$1"
  local credential_label="$2"
  local token=""
  local token_size=0
  local file_size=0

  [[ -f "$credential_path" && ! -L "$credential_path" ]] || \
    aoa_die "existing ${credential_label} must be a regular non-symlink file"
  token="$(<"$credential_path")"
  token_size="${#token}"
  file_size="$(stat -c '%s' "$credential_path")"
  if [[ ! "$token" =~ ^[A-Za-z0-9._~-]{43,512}$ ]] || \
    ! ((file_size == token_size || file_size == token_size + 1)); then
    aoa_die "existing ${credential_label} has invalid content"
  fi
  chmod 0600 "$credential_path"
}

aoa_provision_mcp_bearer() {
  local credential_name="$1"
  local credential_label="$2"
  local credential_path="${mcp_http_secret_dir}/${credential_name}"
  local temp_path=""

  if [[ -e "$mcp_http_secret_dir" || -L "$mcp_http_secret_dir" ]]; then
    [[ -d "$mcp_http_secret_dir" && ! -L "$mcp_http_secret_dir" ]] || \
      aoa_die "MCP HTTP secret root must be a directory, not a symlink"
  else
    install -d -m 0700 "$mcp_http_secret_dir"
  fi
  if [[ -e "$credential_path" || -L "$credential_path" ]]; then
    aoa_validate_mcp_bearer_file "$credential_path" "$credential_label"
    aoa_note "${credential_label} already provisioned under the deployed Secrets root"
    return 0
  fi

  temp_path="$(mktemp "${mcp_http_secret_dir}/.${credential_name}.XXXXXX")"
  if ! aoa_run_isolated_python python3 \
    -c 'import secrets; print(secrets.token_urlsafe(48))' > "$temp_path"; then
    rm -f -- "$temp_path"
    aoa_die "failed to generate MCP HTTP bearer credential"
  fi
  chmod 0600 "$temp_path"
  if ln -- "$temp_path" "$credential_path" 2>/dev/null; then
    rm -f -- "$temp_path"
    aoa_note "provisioned ${credential_label} under the deployed Secrets root"
    return 0
  fi
  rm -f -- "$temp_path"
  if [[ ! -e "$credential_path" && ! -L "$credential_path" ]]; then
    aoa_die "failed to atomically provision ${credential_label}"
  fi
  aoa_validate_mcp_bearer_file "$credential_path" "$credential_label"
  aoa_note "${credential_label} already provisioned under the deployed Secrets root"
}

aoa_provision_mcp_http_auth() {
  aoa_provision_mcp_bearer \
    "$mcp_http_credential_name" \
    "MCP HTTP bearer credential"
}

aoa_provision_abyss_stack_mcp_auth() {
  local read_path="${mcp_http_secret_dir}/${abyss_stack_mcp_read_credential_name}"
  local candidate_path="${mcp_http_secret_dir}/${abyss_stack_mcp_candidate_credential_name}"
  local read_token=""
  local candidate_token=""

  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_read_credential_name" \
    "abyss-stack MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_candidate_credential_name" \
    "abyss-stack MCP candidate bearer credential"
  read_token="$(<"$read_path")"
  candidate_token="$(<"$candidate_path")"
  [[ "$read_token" != "$candidate_token" ]] || \
    aoa_die "abyss-stack MCP read and candidate bearer credentials must be distinct"
}

aoa_require_abyss_stack_mcp_units_stopped() {
  local unit=""
  local unit_properties=""
  local unit_load_state=""
  local unit_state=""
  local unit_fragment_path=""
  local unit_exec_start=""
  local expected_unit_source=""
  local expected_unit_target=""
  local resolved_unit_source=""
  local resolved_unit_fragment=""
  local expected_exec_start=""

  abyss_stack_mcp_units_error=""
  for unit in abyss-stack-mcp-read.service abyss-stack-mcp-candidate.service; do
    expected_unit_source="${AOA_CONFIGS_ROOT}/systemd/user/${unit}"
    expected_unit_target="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user/${unit}"
    expected_exec_start="/usr/bin/flock --shared --no-fork ${abyss_stack_mcp_source_lock} /usr/bin/flock --shared --no-fork ${abyss_stack_mcp_runtime_lock} /usr/bin/env ${AOA_CONFIGS_ROOT}/scripts/aoa-install-systemd --launch-verified-abyss-stack-mcp"
    if [[ ! -f "$expected_unit_source" || -L "$expected_unit_source" ]]; then
      abyss_stack_mcp_units_error="lock-aware source unit is unavailable for ${unit}; link and reload managed user units before provisioning"
      return 1
    fi
    if ! grep -Fqx -- "ExecStart=${expected_exec_start}" \
        "$expected_unit_source"; then
      abyss_stack_mcp_units_error="managed source unit is not lock-aware for ${unit}; refusing runtime replacement"
      return 1
    fi
    if [[ ! -L "$expected_unit_target" || \
          "$(readlink -- "$expected_unit_target" 2>/dev/null)" != \
            "$expected_unit_source" ]]; then
      abyss_stack_mcp_units_error="managed lock-aware unit is not linked for ${unit}; link and reload managed user units before provisioning"
      return 1
    fi
    if ! unit_properties="$(
      systemctl --user show \
        --no-pager \
        --property=LoadState \
        --property=ActiveState \
        --property=FragmentPath \
        --property=ExecStart \
        "$unit"
    )"; then
      abyss_stack_mcp_units_error="cannot inspect the loaded definition for ${unit}; refusing runtime replacement"
      return 1
    fi
    unit_load_state="$(
      awk -F= '$1 == "LoadState" {print substr($0, index($0, "=") + 1)}' \
        <<< "$unit_properties"
    )"
    unit_state="$(
      awk -F= '$1 == "ActiveState" {print substr($0, index($0, "=") + 1)}' \
        <<< "$unit_properties"
    )"
    unit_fragment_path="$(
      awk -F= '$1 == "FragmentPath" {print substr($0, index($0, "=") + 1)}' \
        <<< "$unit_properties"
    )"
    unit_exec_start="$(
      awk -F= '$1 == "ExecStart" {print substr($0, index($0, "=") + 1)}' \
        <<< "$unit_properties"
    )"
    if [[ "$unit_load_state" != "loaded" || -z "$unit_fragment_path" ]]; then
      abyss_stack_mcp_units_error="${unit} is not loaded; link and reload managed user units before provisioning"
      return 1
    fi
    resolved_unit_source="$(readlink -f -- "$expected_unit_source")" || {
      abyss_stack_mcp_units_error="cannot resolve the lock-aware source for ${unit}; refusing runtime replacement"
      return 1
    }
    resolved_unit_fragment="$(readlink -f -- "$unit_fragment_path")" || {
      abyss_stack_mcp_units_error="cannot resolve the loaded fragment for ${unit}; refusing runtime replacement"
      return 1
    }
    if [[ "$resolved_unit_fragment" != "$resolved_unit_source" ]]; then
      abyss_stack_mcp_units_error="${unit} is loaded from an unexpected fragment; link and reload managed user units before provisioning"
      return 1
    fi
    if [[ "$unit_exec_start" != \
          "{ path=/usr/bin/flock ; argv[]=${expected_exec_start} ;"* ]]; then
      abyss_stack_mcp_units_error="${unit} is not loaded with the lock-aware ExecStart; run daemon-reload before provisioning"
      return 1
    fi
    case "$unit_state" in
      inactive|failed)
        ;;
      active|activating|reloading|deactivating)
        abyss_stack_mcp_units_error="refusing to replace abyss-stack MCP runtime while ${unit} is ${unit_state}"
        return 1
        ;;
      *)
        abyss_stack_mcp_units_error="unexpected ${unit} active state ${unit_state}; refusing runtime replacement"
        return 1
        ;;
    esac
  done
}

aoa_digest_abyss_stack_mcp_package() {
  local package_root="$1"
  local digest=""

  digest="$(
    cd "$package_root"
    find . -type f \
        ! -path '*/__pycache__/*' \
        ! -path '*/.pytest_cache/*' \
        ! -name '*.pyc' \
        -print0 |
        LC_ALL=C sort -z |
        xargs -0 sha256sum |
        sha256sum |
        cut -d' ' -f1
  )" || return 1
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$digest"
}

aoa_digest_abyss_stack_mcp_runtime() {
  local runtime_root="$1"
  local digest=""
  local resolved_interpreter=""
  local interpreter_digest=""

  [[ -d "$runtime_root" && ! -L "$runtime_root" ]] || return 1
  resolved_interpreter="$(
    readlink -f -- "${runtime_root}/bin/python"
  )" || return 1
  [[ "$resolved_interpreter" == /* && \
     -f "$resolved_interpreter" && \
     ! -L "$resolved_interpreter" && \
     -x "$resolved_interpreter" ]] || return 1
  interpreter_digest="$(
    sha256sum -- "$resolved_interpreter" | cut -d' ' -f1
  )" || return 1
  [[ "$interpreter_digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  if [[ -n "$(
    find "$runtime_root" \
      ! -type f \
      ! -type d \
      ! -type l \
      -print \
      -quit
  )" ]]; then
    return 1
  fi
  digest="$(
    cd "$runtime_root"
    {
      printf 'i\0./bin/python\0%s\0' "$interpreter_digest"
      while IFS= read -r -d '' entry; do
        local entry_type="${entry%% *}"
        local entry_path="${entry#* }"
        local entry_digest=""

        if [[ "$entry_type" == "l" ]]; then
          entry_digest="$(
            readlink --zero -- "$entry_path" |
              sha256sum |
              cut -d' ' -f1
          )" || exit 1
        else
          entry_digest="$(
            sha256sum -- "$entry_path" | cut -d' ' -f1
          )" || exit 1
        fi
        [[ "$entry_digest" =~ ^[0-9a-f]{64}$ ]] || exit 1
        printf '%s\0%s\0%s\0' "$entry_type" "$entry_path" "$entry_digest"
      done < <(
        find . \
          ! -name '.abyss-stack-mcp-runtime-identity' \
          ! -name '.abyss-stack-mcp-runtime-content-digest' \
          \( -type f -o -type l \) \
          -printf '%y %p\0' |
          LC_ALL=C sort -z
      )
    } |
      sha256sum |
      cut -d' ' -f1
  )" || return 1
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$digest"
}

aoa_verify_abyss_stack_mcp_runtime() {
  local marker=".abyss-stack-mcp-runtime-identity"
  local content_marker=".abyss-stack-mcp-runtime-content-digest"
  local lock_path="${abyss_stack_mcp_service_root}/requirements.lock"
  local source_digest=""
  local lock_digest=""
  local expected_identity=""
  local recorded_identity=""
  local recorded_content_digest=""
  local observed_content_digest=""
  local source_lock_fd=""
  local runtime_lock_fd=""

  [[ -f "$abyss_stack_mcp_source_lock" && \
     ! -L "$abyss_stack_mcp_source_lock" ]] || \
    aoa_die "abyss-stack MCP source projection lock is unavailable"
  [[ -f "$abyss_stack_mcp_runtime_lock" && \
     ! -L "$abyss_stack_mcp_runtime_lock" ]] || \
    aoa_die "abyss-stack MCP runtime lock is unavailable"
  exec {source_lock_fd}<> "$abyss_stack_mcp_source_lock"
  if ! /usr/bin/flock --shared --nonblock "$source_lock_fd"; then
    aoa_die "Configs sync or runtime provisioning holds the abyss-stack MCP source projection lock"
  fi
  exec {runtime_lock_fd}<> "$abyss_stack_mcp_runtime_lock"
  if ! /usr/bin/flock --shared --nonblock "$runtime_lock_fd"; then
    aoa_die "runtime provisioning holds the abyss-stack MCP runtime lock"
  fi
  [[ -d "$abyss_stack_mcp_service_root" && \
     ! -L "$abyss_stack_mcp_service_root" ]] || \
    aoa_die "deployed abyss-stack MCP package root is unavailable"
  [[ -f "${abyss_stack_mcp_service_root}/pyproject.toml" && \
     ! -L "${abyss_stack_mcp_service_root}/pyproject.toml" ]] || \
    aoa_die "deployed abyss-stack MCP package metadata is unavailable"
  [[ -f "$lock_path" && ! -L "$lock_path" ]] || \
    aoa_die "deployed abyss-stack MCP hash lock is unavailable"
  if [[ -n "$(
    find "$abyss_stack_mcp_service_root" \
      ! -type f \
      ! -type d \
      -print \
      -quit
  )" ]]; then
    aoa_die "deployed abyss-stack MCP package must contain only regular files and directories"
  fi
  [[ -d "$abyss_stack_mcp_venv" && ! -L "$abyss_stack_mcp_venv" ]] || \
    aoa_die "provisioned abyss-stack MCP runtime is unavailable"
  [[ -f "${abyss_stack_mcp_venv}/${marker}" && \
     ! -L "${abyss_stack_mcp_venv}/${marker}" ]] || \
    aoa_die "abyss-stack MCP runtime identity marker is unavailable"
  [[ -f "${abyss_stack_mcp_venv}/${content_marker}" && \
     ! -L "${abyss_stack_mcp_venv}/${content_marker}" ]] || \
    aoa_die "abyss-stack MCP runtime content marker is unavailable"

  source_digest="$(
    aoa_digest_abyss_stack_mcp_package "$abyss_stack_mcp_service_root"
  )" || aoa_die "failed to digest the deployed abyss-stack MCP package"
  lock_digest="$(sha256sum "$lock_path" | cut -d' ' -f1)"
  [[ "$lock_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "failed to digest the deployed abyss-stack MCP hash lock"
  expected_identity="${source_digest}:${lock_digest}"
  recorded_identity="$(<"${abyss_stack_mcp_venv}/${marker}")"
  [[ "$recorded_identity" =~ ^[0-9a-f]{64}:[0-9a-f]{64}$ ]] || \
    aoa_die "abyss-stack MCP runtime identity marker is invalid"
  [[ "$recorded_identity" == "$expected_identity" ]] || \
    aoa_die "abyss-stack MCP runtime source-and-lock identity mismatch"

  recorded_content_digest="$(
    <"${abyss_stack_mcp_venv}/${content_marker}"
  )"
  [[ "$recorded_content_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "abyss-stack MCP runtime content marker is invalid"
  observed_content_digest="$(
    aoa_digest_abyss_stack_mcp_runtime "$abyss_stack_mcp_venv"
  )" || aoa_die "failed to digest the provisioned abyss-stack MCP runtime"
  [[ "$observed_content_digest" == "$recorded_content_digest" ]] || \
    aoa_die "abyss-stack MCP runtime content digest mismatch"
  exec {runtime_lock_fd}>&-
  exec {source_lock_fd}>&-
}

aoa_launch_verified_abyss_stack_mcp() {
  aoa_verify_abyss_stack_mcp_runtime
  exec /usr/bin/env -u PYTHONHOME -u PYTHONPATH \
    "$abyss_stack_mcp_venv/bin/python" \
    -I -B -m abyss_stack_mcp.server
}

aoa_rewrite_abyss_stack_mcp_entrypoint_shebangs() {
  local staged_root="$1"
  local published_root="$2"
  local entry=""
  local first_line=""
  local interpreter_suffix=""
  local rewrite_path=""

  while IFS= read -r -d '' entry; do
    IFS= read -r first_line < "$entry" || continue
    [[ "$first_line" == "#!${staged_root}/bin/python"* ]] || continue
    interpreter_suffix="${first_line#\#!"${staged_root}"}"
    [[ "$interpreter_suffix" =~ ^/bin/python([0-9]+([.][0-9]+)*)?([[:space:]].*)?$ ]] || \
      return 1
    rewrite_path="$(mktemp "${entry}.rewrite.XXXXXX")" || return 1
    if ! {
      printf '#!%s%s\n' "$published_root" "$interpreter_suffix"
      tail -n +2 -- "$entry"
    } > "$rewrite_path"; then
      rm -f -- "$rewrite_path"
      return 1
    fi
    chmod --reference="$entry" "$rewrite_path" || {
      rm -f -- "$rewrite_path"
      return 1
    }
    mv -- "$rewrite_path" "$entry" || {
      rm -f -- "$rewrite_path"
      return 1
    }
  done < <(
    find "${staged_root}/bin" \
      -maxdepth 1 \
      -type f \
      -print0
  )

  while IFS= read -r -d '' entry; do
    IFS= read -r first_line < "$entry" || continue
    [[ "$first_line" != "#!${staged_root}/"* ]] || return 1
  done < <(
    find "${staged_root}/bin" \
      -maxdepth 1 \
      -type f \
      -print0
  )
}

aoa_provision_abyss_stack_mcp_runtime() {
  local source_digest=""
  local deployed_digest=""
  local snapshot_digest=""
  local lock_digest=""
  local snapshot_lock_digest=""
  local runtime_identity=""
  local existing_identity=""
  local runtime_content_digest=""
  local existing_content_digest=""
  local observed_content_digest=""
  local marker=".abyss-stack-mcp-runtime-identity"
  local content_marker=".abyss-stack-mcp-runtime-content-digest"
  local lock_path="${abyss_stack_mcp_service_root}/requirements.lock"
  local snapshot_lock_path=""
  local source_snapshot=""
  local temp_venv=""
  local backup_venv=""
  local resolved_bootstrap_python=""
  local runtime_lock_fd=""
  local source_lock_fd=""

  [[ "$abyss_stack_mcp_bootstrap_python" == /* ]] || \
    aoa_die "ABYSS_STACK_MCP_BOOTSTRAP_PYTHON must be an absolute path"
  resolved_bootstrap_python="$(
    readlink -f -- "$abyss_stack_mcp_bootstrap_python"
  )" || aoa_die "failed to resolve abyss-stack MCP bootstrap Python"
  [[ "$resolved_bootstrap_python" == /* && \
     -f "$resolved_bootstrap_python" && \
     ! -L "$resolved_bootstrap_python" && \
     -x "$resolved_bootstrap_python" ]] || \
    aoa_die "abyss-stack MCP bootstrap Python is not an executable regular file"
  abyss_stack_mcp_bootstrap_python="$resolved_bootstrap_python"
  if [[ -e "$abyss_stack_mcp_source_lock_root" || \
        -L "$abyss_stack_mcp_source_lock_root" ]]; then
    [[ -d "$abyss_stack_mcp_source_lock_root" && \
       ! -L "$abyss_stack_mcp_source_lock_root" ]] || \
      aoa_die "abyss-stack MCP source projection lock root must be a non-symlink directory"
  else
    install -d -m 0750 "$abyss_stack_mcp_source_lock_root"
  fi
  if [[ -e "$abyss_stack_mcp_source_lock" || \
        -L "$abyss_stack_mcp_source_lock" ]]; then
    [[ -f "$abyss_stack_mcp_source_lock" && \
       ! -L "$abyss_stack_mcp_source_lock" ]] || \
      aoa_die "abyss-stack MCP source projection lock must be a regular non-symlink file"
  else
    (
      umask 077
      set -o noclobber
      : > "$abyss_stack_mcp_source_lock"
    ) 2>/dev/null || true
    [[ -f "$abyss_stack_mcp_source_lock" && \
       ! -L "$abyss_stack_mcp_source_lock" ]] || \
      aoa_die "failed to create the abyss-stack MCP source projection lock"
  fi
  chmod 0600 "$abyss_stack_mcp_source_lock"
  exec {source_lock_fd}<> "$abyss_stack_mcp_source_lock"
  if ! /usr/bin/flock --exclusive --nonblock "$source_lock_fd"; then
    aoa_die "Configs sync or another provisioner holds the abyss-stack MCP source projection lock"
  fi
  [[ -d "$abyss_stack_mcp_service_root" && \
     ! -L "$abyss_stack_mcp_service_root" ]] || \
    aoa_die "deployed abyss-stack MCP package root is unavailable"
  [[ -f "${abyss_stack_mcp_service_root}/pyproject.toml" && \
     ! -L "${abyss_stack_mcp_service_root}/pyproject.toml" ]] || \
    aoa_die "deployed abyss-stack MCP package metadata is unavailable"
  [[ -f "$lock_path" && ! -L "$lock_path" ]] || \
    aoa_die "deployed abyss-stack MCP hash lock is unavailable"
  if [[ -n "$(
    find "$abyss_stack_mcp_service_root" \
      ! -type f \
      ! -type d \
      -print \
      -quit
  )" ]]; then
    aoa_die "deployed abyss-stack MCP package must contain only regular files and directories"
  fi

  source_digest="$(
    aoa_digest_abyss_stack_mcp_package "$abyss_stack_mcp_service_root"
  )" || \
    aoa_die "failed to digest the deployed abyss-stack MCP package"
  lock_digest="$(sha256sum "$lock_path" | cut -d' ' -f1)"
  [[ "$lock_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "failed to digest the deployed abyss-stack MCP hash lock"
  runtime_identity="${source_digest}:${lock_digest}"

  if [[ -e "$abyss_stack_mcp_runtime_root" || \
        -L "$abyss_stack_mcp_runtime_root" ]]; then
    [[ -d "$abyss_stack_mcp_runtime_root" && \
       ! -L "$abyss_stack_mcp_runtime_root" ]] || \
      aoa_die "abyss-stack MCP runtime root must be a non-symlink directory"
  else
    install -d -m 0750 "$abyss_stack_mcp_runtime_root"
  fi
  if [[ -e "$abyss_stack_mcp_runtime_lock" || \
        -L "$abyss_stack_mcp_runtime_lock" ]]; then
    [[ -f "$abyss_stack_mcp_runtime_lock" && \
       ! -L "$abyss_stack_mcp_runtime_lock" ]] || \
      aoa_die "abyss-stack MCP runtime lock must be a regular non-symlink file"
  else
    (
      umask 077
      set -o noclobber
      : > "$abyss_stack_mcp_runtime_lock"
    ) 2>/dev/null || true
    [[ -f "$abyss_stack_mcp_runtime_lock" && \
       ! -L "$abyss_stack_mcp_runtime_lock" ]] || \
      aoa_die "failed to create the abyss-stack MCP runtime lock"
  fi
  chmod 0600 "$abyss_stack_mcp_runtime_lock"

  if [[ -e "$abyss_stack_mcp_venv" || -L "$abyss_stack_mcp_venv" ]]; then
    [[ -d "$abyss_stack_mcp_venv" && ! -L "$abyss_stack_mcp_venv" ]] || \
      aoa_die "existing abyss-stack MCP runtime must be a non-symlink directory"
    if [[ -f "${abyss_stack_mcp_venv}/${marker}" && \
          ! -L "${abyss_stack_mcp_venv}/${marker}" ]]; then
      existing_identity="$(<"${abyss_stack_mcp_venv}/${marker}")"
    fi
    if [[ -f "${abyss_stack_mcp_venv}/${content_marker}" && \
          ! -L "${abyss_stack_mcp_venv}/${content_marker}" ]]; then
      existing_content_digest="$(
        <"${abyss_stack_mcp_venv}/${content_marker}"
      )"
    fi
    if [[ "$existing_content_digest" =~ ^[0-9a-f]{64}$ ]]; then
      observed_content_digest="$(
        aoa_digest_abyss_stack_mcp_runtime "$abyss_stack_mcp_venv"
      )" || observed_content_digest=""
    fi
    if [[ "$existing_identity" == "$runtime_identity" && \
          "$observed_content_digest" == "$existing_content_digest" && \
          -x "${abyss_stack_mcp_venv}/bin/python" ]] && \
       PYTHONDONTWRITEBYTECODE=1 \
         aoa_run_isolated_python \
           "${abyss_stack_mcp_venv}/bin/python" -m pip check >/dev/null && \
       PYTHONDONTWRITEBYTECODE=1 \
         aoa_run_isolated_python "${abyss_stack_mcp_venv}/bin/python" -c \
           'import abyss_stack_mcp, mcp, pydantic' >/dev/null; then
      deployed_digest="$(
        aoa_digest_abyss_stack_mcp_package "$abyss_stack_mcp_service_root"
      )" || \
        aoa_die "failed to recheck the deployed abyss-stack MCP package"
      [[ "$deployed_digest" == "$source_digest" ]] || \
        aoa_die "deployed abyss-stack MCP package changed during runtime verification"
      aoa_note "abyss-stack MCP runtime already provisioned for deployed source ${source_digest} and lock ${lock_digest}"
      exec {source_lock_fd}>&-
      return 0
    fi
  fi

  exec {runtime_lock_fd}<> "$abyss_stack_mcp_runtime_lock"
  if ! /usr/bin/flock --exclusive --nonblock "$runtime_lock_fd"; then
    aoa_die "another provisioner or a managed abyss-stack MCP plane holds the runtime lock"
  fi
  if ! aoa_require_abyss_stack_mcp_units_stopped; then
    aoa_die "$abyss_stack_mcp_units_error"
  fi

  temp_venv="$(mktemp -d "${abyss_stack_mcp_runtime_root}/.venv.XXXXXX")"
  if ! aoa_run_isolated_python \
    "$abyss_stack_mcp_bootstrap_python" -m venv "$temp_venv"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to create the abyss-stack MCP runtime environment"
  fi
  source_snapshot="${temp_venv}/.source-snapshot"
  install -d -m 0700 "$source_snapshot"
  if ! cp -a -- "${abyss_stack_mcp_service_root}/." "$source_snapshot"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to stage the deployed abyss-stack MCP package snapshot"
  fi
  if [[ -n "$(
    find "$source_snapshot" \
      ! -type f \
      ! -type d \
      -print \
      -quit
  )" ]]; then
    rm -rf -- "$temp_venv"
    aoa_die "staged abyss-stack MCP package snapshot contains a non-regular entry"
  fi
  snapshot_digest="$(
    aoa_digest_abyss_stack_mcp_package "$source_snapshot"
  )" || {
    rm -rf -- "$temp_venv"
    aoa_die "failed to digest the staged abyss-stack MCP package snapshot"
  }
  if [[ "$snapshot_digest" != "$source_digest" ]]; then
    rm -rf -- "$temp_venv"
    aoa_die "deployed abyss-stack MCP package changed while staging its runtime snapshot"
  fi
  snapshot_lock_path="${source_snapshot}/requirements.lock"
  snapshot_lock_digest="$(sha256sum "$snapshot_lock_path" | cut -d' ' -f1)"
  if [[ "$snapshot_lock_digest" != "$lock_digest" ]]; then
    rm -rf -- "$temp_venv"
    aoa_die "deployed abyss-stack MCP hash lock changed while staging its runtime snapshot"
  fi
  if ! PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    aoa_run_isolated_python "${temp_venv}/bin/python" -m pip install \
      --no-input \
      --no-compile \
      --require-hashes \
      -r "$snapshot_lock_path"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to install the deployed abyss-stack MCP hash-locked dependency closure"
  fi
  if ! PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    aoa_run_isolated_python "${temp_venv}/bin/python" -m pip install \
      --no-input \
      --no-compile \
      --no-deps \
      --no-build-isolation \
      "$source_snapshot"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to install the deployed abyss-stack MCP package"
  fi
  if ! PYTHONDONTWRITEBYTECODE=1 \
       aoa_run_isolated_python \
         "${temp_venv}/bin/python" -m pip check >/dev/null || \
     ! PYTHONDONTWRITEBYTECODE=1 \
       aoa_run_isolated_python "${temp_venv}/bin/python" -c \
         'import abyss_stack_mcp, mcp, pydantic' >/dev/null; then
    rm -rf -- "$temp_venv"
    aoa_die "provisioned abyss-stack MCP runtime failed dependency verification"
  fi
  deployed_digest="$(
    aoa_digest_abyss_stack_mcp_package "$abyss_stack_mcp_service_root"
  )" || {
    rm -rf -- "$temp_venv"
    aoa_die "failed to recheck the deployed abyss-stack MCP package"
  }
  if [[ "$deployed_digest" != "$source_digest" ]]; then
    rm -rf -- "$temp_venv"
    aoa_die "deployed abyss-stack MCP package changed during runtime provisioning"
  fi
  rm -rf -- "$source_snapshot"
  if ! aoa_rewrite_abyss_stack_mcp_entrypoint_shebangs \
    "$temp_venv" \
    "$abyss_stack_mcp_venv"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to bind abyss-stack MCP entry points to the published runtime"
  fi
  runtime_content_digest="$(
    aoa_digest_abyss_stack_mcp_runtime "$temp_venv"
  )" || {
    rm -rf -- "$temp_venv"
    aoa_die "failed to digest the provisioned abyss-stack MCP runtime"
  }
  printf '%s\n' "$runtime_content_digest" > "${temp_venv}/${content_marker}"
  chmod 0644 "${temp_venv}/${content_marker}"
  printf '%s\n' "$runtime_identity" > "${temp_venv}/${marker}"
  chmod 0644 "${temp_venv}/${marker}"

  if ! aoa_require_abyss_stack_mcp_units_stopped; then
    rm -rf -- "$temp_venv"
    aoa_die "$abyss_stack_mcp_units_error"
  fi
  if [[ -d "$abyss_stack_mcp_venv" ]]; then
    backup_venv="$(mktemp -d "${abyss_stack_mcp_runtime_root}/.venv.previous.XXXXXX")"
    rmdir -- "$backup_venv"
    mv -- "$abyss_stack_mcp_venv" "$backup_venv"
  fi
  if ! mv -- "$temp_venv" "$abyss_stack_mcp_venv"; then
    if [[ -n "$backup_venv" && -d "$backup_venv" ]]; then
      mv -- "$backup_venv" "$abyss_stack_mcp_venv"
    fi
    rm -rf -- "$temp_venv"
    aoa_die "failed to activate the provisioned abyss-stack MCP runtime"
  fi
  if [[ -n "$backup_venv" && -d "$backup_venv" ]]; then
    rm -rf -- "$backup_venv"
  fi
  exec {runtime_lock_fd}>&-
  exec {source_lock_fd}>&-
  aoa_note "provisioned abyss-stack MCP runtime for deployed source ${source_digest} and lock ${lock_digest}"
}

aoa_validate_mcp_http_codex_zshrc() {
  local start_count=0
  local end_count=0
  local start_line=0
  local end_line=0

  mcp_http_codex_block_present=0
  if [[ ! -e "$mcp_http_codex_zshrc" && ! -L "$mcp_http_codex_zshrc" ]]; then
    return 0
  fi
  [[ -f "$mcp_http_codex_zshrc" && ! -L "$mcp_http_codex_zshrc" ]] || \
    aoa_die "Codex client install target must be a regular non-symlink .zshrc"

  start_count="$(grep -Fxc -- "$mcp_http_codex_block_start" "$mcp_http_codex_zshrc" || true)"
  end_count="$(grep -Fxc -- "$mcp_http_codex_block_end" "$mcp_http_codex_zshrc" || true)"
  if ((start_count == 0 && end_count == 0)); then
    return 0
  fi
  if ((start_count != 1 || end_count != 1)); then
    aoa_die "managed MCP HTTP Codex client block in .zshrc is malformed"
  fi
  start_line="$(grep -Fn -- "$mcp_http_codex_block_start" "$mcp_http_codex_zshrc" | cut -d: -f1)"
  end_line="$(grep -Fn -- "$mcp_http_codex_block_end" "$mcp_http_codex_zshrc" | cut -d: -f1)"
  ((start_line < end_line)) || aoa_die "managed MCP HTTP Codex client block in .zshrc is malformed"
  mcp_http_codex_block_present=1
}

aoa_render_zshrc_without_mcp_http_codex_client() {
  local line=""
  local in_block=0

  if [[ ! -e "$mcp_http_codex_zshrc" ]]; then
    return 0
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$mcp_http_codex_block_start" ]]; then
      in_block=1
      continue
    fi
    if [[ "$line" == "$mcp_http_codex_block_end" ]]; then
      in_block=0
      continue
    fi
    ((in_block)) || printf '%s\n' "$line"
  done < "$mcp_http_codex_zshrc"
}

aoa_write_mcp_http_codex_zshrc() {
  local mode="$1"
  local target_dir=""
  local temp_path=""

  aoa_validate_mcp_http_codex_zshrc
  target_dir="$(dirname -- "$mcp_http_codex_zshrc")"
  mkdir -p -- "$target_dir"
  temp_path="$(mktemp "${target_dir}/.zshrc.abyss-stack.XXXXXX")"
  if ! aoa_render_zshrc_without_mcp_http_codex_client > "$temp_path"; then
    rm -f -- "$temp_path"
    aoa_die "failed to prepare the MCP HTTP Codex client .zshrc update"
  fi

  if [[ "$mode" == "install" ]]; then
    [[ -f "$mcp_http_codex_launcher" && ! -L "$mcp_http_codex_launcher" && -x "$mcp_http_codex_launcher" ]] || {
      rm -f -- "$temp_path"
      aoa_die "deployed MCP HTTP Codex client launcher is unavailable: ${mcp_http_codex_launcher}"
    }
    {
      printf '%s\n' "$mcp_http_codex_block_start"
      printf 'function codex {\n'
      printf '  command %q "$@"\n' "$mcp_http_codex_launcher"
      printf '}\n'
      printf '%s\n' "$mcp_http_codex_block_end"
    } >> "$temp_path"
  elif [[ "$mode" != "remove" ]]; then
    rm -f -- "$temp_path"
    aoa_die "invalid MCP HTTP Codex client .zshrc update mode"
  fi

  if [[ -e "$mcp_http_codex_zshrc" ]]; then
    chmod --reference="$mcp_http_codex_zshrc" "$temp_path"
  else
    chmod 0644 "$temp_path"
  fi
  if ! mv -- "$temp_path" "$mcp_http_codex_zshrc"; then
    rm -f -- "$temp_path"
    aoa_die "failed to install the MCP HTTP Codex client .zshrc update"
  fi
}

aoa_install_mcp_http_codex_client() {
  aoa_write_mcp_http_codex_zshrc install
  aoa_note "MCP HTTP Codex client installed for new interactive Zsh launches"
  aoa_note "existing shells and running Codex processes were not changed"
}

aoa_remove_mcp_http_codex_client() {
  aoa_validate_mcp_http_codex_zshrc
  if ((!mcp_http_codex_block_present)); then
    aoa_note "MCP HTTP Codex client block is already absent from .zshrc"
    return 0
  fi
  aoa_write_mcp_http_codex_zshrc remove
  aoa_note "MCP HTTP Codex client removed from future interactive Zsh launches"
  aoa_note "existing shells and running Codex processes were not changed"
}

if ((provision_mcp_http_auth || install_mcp_http_codex_client)); then
  aoa_provision_mcp_http_auth
fi
if ((provision_abyss_stack_mcp_auth)); then
  aoa_provision_abyss_stack_mcp_auth
fi
if ((provision_abyss_stack_mcp_runtime)); then
  aoa_provision_abyss_stack_mcp_runtime
fi
if ((verify_abyss_stack_mcp_runtime)); then
  aoa_verify_abyss_stack_mcp_runtime
fi
if ((launch_verified_abyss_stack_mcp)); then
  aoa_launch_verified_abyss_stack_mcp
fi
if ((install_mcp_http_codex_client)); then
  aoa_install_mcp_http_codex_client
fi
if ((remove_mcp_http_codex_client)); then
  aoa_remove_mcp_http_codex_client
fi
if ((provision_mcp_http_auth || provision_abyss_stack_mcp_auth || provision_abyss_stack_mcp_runtime || verify_abyss_stack_mcp_runtime || launch_verified_abyss_stack_mcp || install_mcp_http_codex_client || remove_mcp_http_codex_client)) && \
  ((!enable_now && !restart_now && !link_all_user_units && !link_system_units && !selection_set && !overlay_set)); then
  exit 0
fi

unit_source="${AOA_CONFIGS_ROOT}/systemd/user/podman-compose-abyss.service"
unit_manifest="${AOA_CONFIGS_ROOT}/systemd/user/managed-units.txt"
system_unit_manifest="${AOA_CONFIGS_ROOT}/systemd/system/managed-units.txt"
unit_target_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
unit_target="${unit_target_dir}/podman-compose-abyss.service"
selection_dropin_dir="${unit_target_dir}/podman-compose-abyss.service.d"
selection_dropin="${selection_dropin_dir}/20-runtime-selection.conf"
runtime_lifecycle_dropin_source="${AOA_CONFIGS_ROOT}/systemd/user/podman-compose-abyss.service.d/99-runtime-lifecycle.conf"
runtime_lifecycle_dropin="${selection_dropin_dir}/99-runtime-lifecycle.conf"
backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"

[[ -f "$unit_source" ]] || aoa_die "unit source not found: $unit_source"

aoa_link_system_unit() {
  local unit_name="$1"
  local source_path="${AOA_CONFIGS_ROOT}/systemd/system/${unit_name}"
  local target_path="/etc/systemd/system/${unit_name}"
  local backup_path
  local previous_target

  if [[ ! "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.(service|timer|path)$ ]]; then
    aoa_die "invalid unit name in managed system-unit manifest: ${unit_name}"
  fi
  [[ -f "$source_path" ]] || aoa_die "managed system unit source not found: ${source_path}"

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    if [[ -L "$target_path" ]]; then
      previous_target="$(readlink "$target_path" || true)"
      rm -f -- "$target_path"
      aoa_note "replacing system unit symlink with root-owned file: ${target_path} (was ${previous_target})"
    else
      backup_path="${target_path}.pre-abyss-stack-${backup_stamp}"
      cp -a -- "$target_path" "$backup_path"
      aoa_note "backup existing system unit: ${backup_path}"
    fi
  fi

  install -m 0644 -o root -g root "$source_path" "$target_path"
  aoa_note "system unit installed: ${target_path}"
}

if ((link_system_units)); then
  if ((EUID != 0)); then
    aoa_die "--system-units requires root; run via pkexec after scripts/aoa-sync-configs"
  fi
  [[ -f "$system_unit_manifest" ]] || aoa_die "managed system-unit manifest not found: ${system_unit_manifest}"
  while IFS= read -r unit_name || [[ -n "$unit_name" ]]; do
    unit_name="${unit_name%%#*}"
    unit_name="${unit_name#"${unit_name%%[![:space:]]*}"}"
    unit_name="${unit_name%"${unit_name##*[![:space:]]}"}"
    [[ -n "$unit_name" ]] || continue
    aoa_link_system_unit "$unit_name"
  done < "$system_unit_manifest"
  systemctl daemon-reload
  aoa_note "managed system units installed from ${system_unit_manifest}"
  aoa_note "system daemon reloaded; no services or timers were started, stopped, restarted, enabled, disabled, or masked"
  exit 0
fi

mkdir -p "$unit_target_dir"

aoa_link_user_unit() {
  local unit_name="$1"
  local source_path="${AOA_CONFIGS_ROOT}/systemd/user/${unit_name}"
  local target_path="${unit_target_dir}/${unit_name}"
  local backup_path
  local previous_target

  if [[ ! "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.(service|timer|path)$ ]]; then
    aoa_die "invalid unit name in managed user-unit manifest: ${unit_name}"
  fi
  [[ -f "$source_path" ]] || aoa_die "managed user unit source not found: ${source_path}"

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    if [[ -L "$target_path" ]]; then
      previous_target="$(readlink "$target_path" || true)"
      if [[ "$previous_target" == "/dev/null" ]]; then
        aoa_note "preserving masked user unit: ${target_path}"
        return 0
      fi
      if [[ "$previous_target" == "$source_path" ]]; then
        aoa_note "unit already linked: ${target_path}"
        return 0
      fi
      aoa_note "relinking user unit: ${target_path} (was ${previous_target})"
    else
      backup_path="${target_path}.pre-abyss-stack-${backup_stamp}"
      cp -a -- "$target_path" "$backup_path"
      aoa_note "backup existing user unit: ${backup_path}"
    fi
  fi

  ln -sfn "$source_path" "$target_path"
  aoa_note "unit linked: ${target_path}"
}

aoa_link_runtime_lifecycle_dropin() {
  local backup_path
  local previous_target

  if [[ ! -f "$runtime_lifecycle_dropin_source" ]]; then
    aoa_note "runtime lifecycle drop-in source not present; leaving host drop-ins unchanged"
    return 0
  fi

  mkdir -p "$selection_dropin_dir"
  if [[ -e "$runtime_lifecycle_dropin" || -L "$runtime_lifecycle_dropin" ]]; then
    if [[ -L "$runtime_lifecycle_dropin" ]]; then
      previous_target="$(readlink "$runtime_lifecycle_dropin" || true)"
      if [[ "$previous_target" == "$runtime_lifecycle_dropin_source" ]]; then
        aoa_note "runtime lifecycle drop-in already linked: ${runtime_lifecycle_dropin}"
        return 0
      fi
      aoa_note "relinking runtime lifecycle drop-in: ${runtime_lifecycle_dropin} (was ${previous_target})"
    elif [[ -d "$runtime_lifecycle_dropin" ]]; then
      aoa_die "runtime lifecycle drop-in target must not be a directory: ${runtime_lifecycle_dropin}"
    else
      backup_path="${runtime_lifecycle_dropin}.pre-abyss-stack-${backup_stamp}"
      cp -a -- "$runtime_lifecycle_dropin" "$backup_path"
      aoa_note "backup existing runtime lifecycle drop-in: ${backup_path}"
    fi
  fi

  ln -sfn "$runtime_lifecycle_dropin_source" "$runtime_lifecycle_dropin"
  aoa_note "runtime lifecycle drop-in linked: ${runtime_lifecycle_dropin}"
}

if ((link_all_user_units)); then
  [[ -f "$unit_manifest" ]] || aoa_die "managed user-unit manifest not found: ${unit_manifest}"
  while IFS= read -r unit_name || [[ -n "$unit_name" ]]; do
    unit_name="${unit_name%%#*}"
    unit_name="${unit_name#"${unit_name%%[![:space:]]*}"}"
    unit_name="${unit_name%"${unit_name##*[![:space:]]}"}"
    [[ -n "$unit_name" ]] || continue
    aoa_link_user_unit "$unit_name"
  done < "$unit_manifest"
else
  aoa_link_user_unit "podman-compose-abyss.service"
fi
aoa_link_runtime_lifecycle_dropin

if ((selection_set || overlay_set)); then
  mkdir -p "$selection_dropin_dir"
  {
    printf '[Service]\n'
    printf 'Environment=AOA_STACK_PRESET=%s\n' "$preset_spec"
    printf 'Environment=AOA_STACK_PROFILE=%s\n' "$profile_spec"
    printf 'Environment=AOA_EXTRA_COMPOSE_FILES=%s\n' "$overlay_spec"
  } > "$selection_dropin"
  aoa_note "runtime selection drop-in: ${selection_dropin}"
  aoa_note "runtime selection preset: ${preset_spec:-(none)}"
  aoa_note "runtime selection profile: ${profile_spec:-(none)}"
  aoa_note "runtime selection overlays: ${overlay_spec:-(none)}"
fi

systemctl --user daemon-reload

if ((link_all_user_units)); then
  aoa_note "managed user units linked from ${unit_manifest}"
else
  aoa_note "single runtime unit linked: ${unit_target}"
fi

if ((enable_now)); then
  systemctl --user enable --now podman-compose-abyss.service
  aoa_note "unit enabled and started"
else
  aoa_note "unit reloaded but not enabled"
fi

if ((restart_now)); then
  systemctl --user restart podman-compose-abyss.service
  aoa_note "unit restarted"
fi
