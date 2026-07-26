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
if (((install_mcp_http_codex_client || remove_mcp_http_codex_client) && EUID == 0)); then
  aoa_die "MCP HTTP Codex client install and removal must run as the target user, not root"
fi
if ((provision_abyss_stack_mcp_auth && EUID == 0)); then
  aoa_die "abyss-stack MCP credential provisioning must run as the target user, not root"
fi
if ((provision_abyss_stack_mcp_runtime && EUID == 0)); then
  aoa_die "abyss-stack MCP runtime provisioning must run as the target user, not root"
fi

mcp_http_credential_name="aoa-mcp-http-bearer-token"
mcp_http_secret_dir="${AOA_STACK_ROOT}/Secrets/Configs"
abyss_stack_mcp_read_credential_name="abyss-stack-mcp-read-bearer-token"
abyss_stack_mcp_candidate_credential_name="abyss-stack-mcp-candidate-bearer-token"
abyss_stack_mcp_service_root="${AOA_CONFIGS_ROOT}/mcp/services/abyss-stack-mcp"
abyss_stack_mcp_runtime_root="${AOA_STACK_ROOT}/Services/abyss-stack-mcp"
abyss_stack_mcp_venv="${abyss_stack_mcp_runtime_root}/venv"
abyss_stack_mcp_bootstrap_python="${ABYSS_STACK_MCP_BOOTSTRAP_PYTHON:-/usr/bin/python3}"
mcp_http_codex_launcher="${AOA_CONFIGS_ROOT}/mcp/services/_shared/codex_http_client.sh"
mcp_http_codex_zshrc="${ZDOTDIR:-${HOME}}/.zshrc"
mcp_http_codex_block_start="# >>> abyss-stack MCP HTTP Codex client >>>"
mcp_http_codex_block_end="# <<< abyss-stack MCP HTTP Codex client <<<"
mcp_http_codex_block_present=0

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
  if ! /usr/bin/env python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "$temp_path"; then
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
  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_read_credential_name" \
    "abyss-stack MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_candidate_credential_name" \
    "abyss-stack MCP candidate bearer credential"
}

aoa_provision_abyss_stack_mcp_runtime() {
  local source_digest=""
  local lock_digest=""
  local runtime_identity=""
  local existing_identity=""
  local marker=".abyss-stack-mcp-runtime-identity"
  local lock_path="${abyss_stack_mcp_service_root}/requirements.lock"
  local temp_venv=""
  local backup_venv=""
  local resolved_bootstrap_python=""
  local unit=""
  local unit_state=""

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
  [[ -d "$abyss_stack_mcp_service_root" && \
     ! -L "$abyss_stack_mcp_service_root" ]] || \
    aoa_die "deployed abyss-stack MCP package root is unavailable"
  [[ -f "${abyss_stack_mcp_service_root}/pyproject.toml" && \
     ! -L "${abyss_stack_mcp_service_root}/pyproject.toml" ]] || \
    aoa_die "deployed abyss-stack MCP package metadata is unavailable"
  [[ -f "$lock_path" && ! -L "$lock_path" ]] || \
    aoa_die "deployed abyss-stack MCP hash lock is unavailable"
  if [[ -n "$(find "$abyss_stack_mcp_service_root" -type l -print -quit)" ]]; then
    aoa_die "deployed abyss-stack MCP package must not contain symlinks"
  fi

  source_digest="$(
    cd "$abyss_stack_mcp_service_root"
    find . -type f \
        ! -path '*/__pycache__/*' \
        ! -path '*/.pytest_cache/*' \
        ! -name '*.pyc' \
        -print0 |
        LC_ALL=C sort -z |
        xargs -0 sha256sum |
        sha256sum |
        cut -d' ' -f1
  )"
  [[ "$source_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "failed to digest the deployed abyss-stack MCP package"
  lock_digest="$(sha256sum "$lock_path" | cut -d' ' -f1)"
  [[ "$lock_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "failed to digest the deployed abyss-stack MCP hash lock"
  runtime_identity="${source_digest}:${lock_digest}"

  if [[ -e "$abyss_stack_mcp_venv" || -L "$abyss_stack_mcp_venv" ]]; then
    [[ -d "$abyss_stack_mcp_venv" && ! -L "$abyss_stack_mcp_venv" ]] || \
      aoa_die "existing abyss-stack MCP runtime must be a non-symlink directory"
    if [[ -f "${abyss_stack_mcp_venv}/${marker}" ]]; then
      existing_identity="$(<"${abyss_stack_mcp_venv}/${marker}")"
    fi
    if [[ "$existing_identity" == "$runtime_identity" && \
          -x "${abyss_stack_mcp_venv}/bin/python" ]] && \
       "${abyss_stack_mcp_venv}/bin/python" -m pip check >/dev/null && \
       "${abyss_stack_mcp_venv}/bin/python" -c \
         'import abyss_stack_mcp, mcp, pydantic' >/dev/null; then
      aoa_note "abyss-stack MCP runtime already provisioned for deployed source ${source_digest} and lock ${lock_digest}"
      return 0
    fi
  fi

  for unit in abyss-stack-mcp-read.service abyss-stack-mcp-candidate.service; do
    if ! unit_state="$(
      systemctl --user list-units \
        --all \
        --full \
        --plain \
        --no-legend \
        "$unit" |
        awk -v expected="$unit" '$1 == expected {print $3}'
    )"; then
      aoa_die "cannot determine whether ${unit} is active; refusing runtime replacement"
    fi
    case "$unit_state" in
      "")
        ;;
      inactive|failed)
        ;;
      active|activating|reloading|deactivating)
        aoa_die "refusing to replace abyss-stack MCP runtime while ${unit} is ${unit_state}"
        ;;
      *)
        aoa_die "unexpected ${unit} active state ${unit_state}; refusing runtime replacement"
        ;;
    esac
  done

  install -d -m 0750 "$abyss_stack_mcp_runtime_root"
  temp_venv="$(mktemp -d "${abyss_stack_mcp_runtime_root}/.venv.XXXXXX")"
  if ! "$abyss_stack_mcp_bootstrap_python" -m venv "$temp_venv"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to create the abyss-stack MCP runtime environment"
  fi
  if ! PIP_DISABLE_PIP_VERSION_CHECK=1 \
    "${temp_venv}/bin/python" -m pip install \
      --no-input \
      --require-hashes \
      -r "$lock_path"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to install the deployed abyss-stack MCP hash-locked dependency closure"
  fi
  if ! PIP_DISABLE_PIP_VERSION_CHECK=1 \
    "${temp_venv}/bin/python" -m pip install \
      --no-input \
      --no-deps \
      --no-build-isolation \
      "$abyss_stack_mcp_service_root"; then
    rm -rf -- "$temp_venv"
    aoa_die "failed to install the deployed abyss-stack MCP package"
  fi
  if ! "${temp_venv}/bin/python" -m pip check >/dev/null || \
     ! "${temp_venv}/bin/python" -c \
       'import abyss_stack_mcp, mcp, pydantic' >/dev/null; then
    rm -rf -- "$temp_venv"
    aoa_die "provisioned abyss-stack MCP runtime failed dependency verification"
  fi
  printf '%s\n' "$runtime_identity" > "${temp_venv}/${marker}"
  chmod 0644 "${temp_venv}/${marker}"

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
if ((install_mcp_http_codex_client)); then
  aoa_install_mcp_http_codex_client
fi
if ((remove_mcp_http_codex_client)); then
  aoa_remove_mcp_http_codex_client
fi
if ((provision_mcp_http_auth || provision_abyss_stack_mcp_auth || provision_abyss_stack_mcp_runtime || install_mcp_http_codex_client || remove_mcp_http_codex_client)) && \
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
