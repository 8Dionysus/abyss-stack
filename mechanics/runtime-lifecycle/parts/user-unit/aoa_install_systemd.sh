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
provision_organ_mcp_read_auth=0
provision_organ_mcp_candidate_auth=0
provision_abyss_stack_mcp_auth=0
rotate_abyss_stack_mcp_auth=0
provision_ovms_auth=0
provision_abyss_stack_mcp_runtime=0
repair_abyss_stack_mcp_runtime=0
verify_abyss_stack_mcp_runtime=0
verify_abyss_stack_mcp_repair_eligibility=0
launch_verified_abyss_stack_mcp=0
enable_abyss_stack_mcp_auto_repair=0
disable_abyss_stack_mcp_auto_repair=0
verify_abyss_stack_mcp_runtime_contour="all"
launch_verified_abyss_stack_mcp_contour=""
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
    --provision-organ-mcp-read-auth)
      provision_organ_mcp_read_auth=1
      ;;
    --provision-organ-mcp-candidate-auth)
      provision_organ_mcp_candidate_auth=1
      ;;
    --provision-abyss-stack-mcp-auth)
      provision_abyss_stack_mcp_auth=1
      ;;
    --rotate-abyss-stack-mcp-auth)
      rotate_abyss_stack_mcp_auth=1
      ;;
    --provision-ovms-auth)
      provision_ovms_auth=1
      ;;
    --provision-abyss-stack-mcp-runtime)
      provision_abyss_stack_mcp_runtime=1
      ;;
    --repair-abyss-stack-mcp-runtime)
      repair_abyss_stack_mcp_runtime=1
      ;;
    --verify-abyss-stack-mcp-runtime)
      verify_abyss_stack_mcp_runtime=1
      ;;
    --verify-abyss-stack-mcp-runtime=*)
      verify_abyss_stack_mcp_runtime=1
      verify_abyss_stack_mcp_runtime_contour="${1#*=}"
      ;;
    --verify-abyss-stack-mcp-repair-eligibility)
      verify_abyss_stack_mcp_repair_eligibility=1
      ;;
    --launch-verified-abyss-stack-mcp)
      launch_verified_abyss_stack_mcp=1
      ;;
    --launch-verified-abyss-stack-mcp=*)
      launch_verified_abyss_stack_mcp=1
      launch_verified_abyss_stack_mcp_contour="${1#*=}"
      ;;
    --enable-abyss-stack-mcp-auto-repair)
      enable_abyss_stack_mcp_auto_repair=1
      ;;
    --disable-abyss-stack-mcp-auto-repair)
      disable_abyss_stack_mcp_auto_repair=1
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
if ((enable_abyss_stack_mcp_auto_repair && disable_abyss_stack_mcp_auto_repair)); then
  aoa_die "cannot enable and disable abyss-stack MCP auto-repair in one transaction"
fi
if ((repair_abyss_stack_mcp_runtime && \
     (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
      provision_organ_mcp_candidate_auth || provision_abyss_stack_mcp_auth || \
      rotate_abyss_stack_mcp_auth || provision_abyss_stack_mcp_runtime || \
      verify_abyss_stack_mcp_runtime || \
      verify_abyss_stack_mcp_repair_eligibility || \
      launch_verified_abyss_stack_mcp || \
      enable_abyss_stack_mcp_auto_repair || \
      disable_abyss_stack_mcp_auto_repair || \
      install_mcp_http_codex_client || remove_mcp_http_codex_client || \
      enable_now || restart_now || link_all_user_units || link_system_units || \
      selection_set || overlay_set))); then
  aoa_die "abyss-stack MCP runtime repair must be a standalone action"
fi
if (((enable_abyss_stack_mcp_auto_repair || disable_abyss_stack_mcp_auto_repair) && \
      (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
       provision_organ_mcp_candidate_auth || provision_abyss_stack_mcp_auth || \
       rotate_abyss_stack_mcp_auth || provision_abyss_stack_mcp_runtime || \
       repair_abyss_stack_mcp_runtime || \
       verify_abyss_stack_mcp_runtime || launch_verified_abyss_stack_mcp || \
       install_mcp_http_codex_client || remove_mcp_http_codex_client || \
       enable_now || restart_now || link_all_user_units || link_system_units || \
       selection_set || overlay_set))); then
  aoa_die "abyss-stack MCP auto-repair policy changes must be standalone actions"
fi
if ((provision_ovms_auth && \
      (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
       provision_organ_mcp_candidate_auth || provision_abyss_stack_mcp_auth || \
       rotate_abyss_stack_mcp_auth || provision_abyss_stack_mcp_runtime || \
       verify_abyss_stack_mcp_runtime || launch_verified_abyss_stack_mcp || \
       install_mcp_http_codex_client || remove_mcp_http_codex_client || \
       enable_now || restart_now || link_all_user_units || link_system_units || \
       selection_set || overlay_set))); then
  aoa_die "OVMS credential provisioning must be a standalone action"
fi
if ((rotate_abyss_stack_mcp_auth && \
      (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
       provision_organ_mcp_candidate_auth || \
       provision_abyss_stack_mcp_auth || \
       provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime || \
       verify_abyss_stack_mcp_runtime || \
       launch_verified_abyss_stack_mcp || install_mcp_http_codex_client || \
       remove_mcp_http_codex_client || enable_now || restart_now || \
       link_all_user_units || link_system_units || selection_set || overlay_set))); then
  aoa_die "abyss-stack MCP credential rotation must be a standalone action"
fi
if (((provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime) && \
     link_all_user_units)); then
  aoa_die "link lock-aware user units in a separate transaction before abyss-stack MCP runtime provisioning"
fi
if ((verify_abyss_stack_mcp_runtime && \
      (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
       provision_organ_mcp_candidate_auth || \
       provision_abyss_stack_mcp_auth || \
       provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime || \
       install_mcp_http_codex_client || \
       remove_mcp_http_codex_client || enable_now || restart_now || \
       launch_verified_abyss_stack_mcp || link_all_user_units || \
       link_system_units || selection_set || overlay_set))); then
  aoa_die "abyss-stack MCP runtime verification must be a standalone read-only action"
fi
if ((verify_abyss_stack_mcp_repair_eligibility && \
      (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
       provision_organ_mcp_candidate_auth || \
       provision_abyss_stack_mcp_auth || rotate_abyss_stack_mcp_auth || \
       provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime || \
       verify_abyss_stack_mcp_runtime || \
       launch_verified_abyss_stack_mcp || enable_abyss_stack_mcp_auto_repair || \
       disable_abyss_stack_mcp_auto_repair || install_mcp_http_codex_client || \
       remove_mcp_http_codex_client || enable_now || restart_now || \
       link_all_user_units || link_system_units || selection_set || overlay_set))); then
  aoa_die "abyss-stack MCP repair eligibility verification must be a standalone read-only action"
fi
if ((launch_verified_abyss_stack_mcp && \
      (provision_mcp_http_auth || provision_organ_mcp_read_auth || \
       provision_organ_mcp_candidate_auth || \
       provision_abyss_stack_mcp_auth || \
       provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime || \
       verify_abyss_stack_mcp_runtime || \
       install_mcp_http_codex_client || remove_mcp_http_codex_client || \
       enable_now || restart_now || link_all_user_units || link_system_units || \
       selection_set || overlay_set))); then
  aoa_die "verified abyss-stack MCP launch must be a standalone unit action"
fi
if ((verify_abyss_stack_mcp_runtime)); then
  case "$verify_abyss_stack_mcp_runtime_contour" in
    all|read|candidate|internal_effect)
      ;;
    *)
      aoa_die "abyss-stack MCP runtime verification contour must be all, read, candidate, or internal_effect"
      ;;
  esac
fi
if ((launch_verified_abyss_stack_mcp)); then
  if [[ -z "$launch_verified_abyss_stack_mcp_contour" ]]; then
    launch_verified_abyss_stack_mcp_contour="$(
      printf '%s' "${ABYSS_STACK_MCP_POLICY_FAMILY:-}"
    )"
  fi
  case "$launch_verified_abyss_stack_mcp_contour" in
    read|candidate|internal_effect)
      ;;
    *)
      aoa_die "verified abyss-stack MCP launch contour must be read, candidate, or internal_effect"
      ;;
  esac
fi
if (((install_mcp_http_codex_client || remove_mcp_http_codex_client) && EUID == 0)); then
  aoa_die "MCP HTTP Codex client install and removal must run as the target user, not root"
fi
if (((provision_abyss_stack_mcp_auth || rotate_abyss_stack_mcp_auth) && EUID == 0)); then
  aoa_die "abyss-stack MCP credential management must run as the target user, not root"
fi
if ((provision_ovms_auth && EUID == 0)); then
  aoa_die "OVMS credential provisioning must run as the target rootless Podman user, not root"
fi
if (((provision_organ_mcp_read_auth || provision_organ_mcp_candidate_auth) && EUID == 0)); then
  aoa_die "organ MCP credential management must run as the target user, not root"
fi
if (((provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime) && \
     EUID == 0)); then
  aoa_die "abyss-stack MCP runtime provisioning must run as the target user, not root"
fi
if ((launch_verified_abyss_stack_mcp && EUID == 0)); then
  aoa_die "verified abyss-stack MCP launch must run as the target user, not root"
fi
if (((enable_abyss_stack_mcp_auto_repair || disable_abyss_stack_mcp_auto_repair) && EUID == 0)); then
  aoa_die "abyss-stack MCP auto-repair policy changes must run as the target user, not root"
fi

mcp_http_credential_name="aoa-mcp-http-bearer-token"
mcp_http_secret_dir="${AOA_STACK_ROOT}/Secrets/Configs"
abyss_stack_mcp_auto_repair_marker="${mcp_http_secret_dir}/abyss-stack-mcp-runtime-auto-repair.enabled"
ovms_credential_name="abyss-ovms-api-key"
ovms_credential_path="${mcp_http_secret_dir}/ovms_api_key.txt"
aoa_decisions_mcp_read_credential_name="aoa-decisions-mcp-read-bearer-token"
aoa_memo_mcp_read_credential_name="aoa-memo-mcp-read-bearer-token"
aoa_memo_mcp_candidate_credential_name="aoa-memo-mcp-candidate-bearer-token"
aoa_kag_mcp_read_credential_name="aoa-kag-mcp-read-bearer-token"
aoa_4pda_connector_mcp_read_credential_name="aoa-4pda-connector-mcp-read-bearer-token"
aoa_course_connector_mcp_read_credential_name="aoa-course-connector-mcp-read-bearer-token"
aoa_discord_connector_mcp_read_credential_name="aoa-discord-connector-mcp-read-bearer-token"
aoa_session_memory_mcp_read_credential_name="aoa-session-memory-mcp-read-bearer-token"
aoa_stackoverflow_connector_mcp_read_credential_name="aoa-stackoverflow-connector-mcp-read-bearer-token"
aoa_evals_mcp_read_credential_name="aoa-evals-mcp-read-bearer-token"
aoa_evals_mcp_candidate_credential_name="aoa-evals-mcp-candidate-bearer-token"
aoa_stats_mcp_read_credential_name="aoa-stats-mcp-read-bearer-token"
aoa_telegram_connector_mcp_read_credential_name="aoa-telegram-connector-mcp-read-bearer-token"
aoa_xda_connector_mcp_read_credential_name="aoa-xda-connector-mcp-read-bearer-token"
abyss_machine_mcp_read_credential_name="abyss-machine-mcp-read-bearer-token"
tos_corpus_mcp_read_credential_name="tos-corpus-mcp-read-bearer-token"
organ_mcp_read_auth_manifest_name="organ-mcp-read-auth-manifest.json"
organ_mcp_read_auth_manifest_path="${mcp_http_secret_dir}/${organ_mcp_read_auth_manifest_name}"
organ_mcp_candidate_auth_manifest_name="organ-mcp-candidate-auth-manifest.json"
organ_mcp_candidate_auth_manifest_path="${mcp_http_secret_dir}/${organ_mcp_candidate_auth_manifest_name}"
abyss_stack_mcp_read_credential_name="abyss-stack-mcp-read-bearer-token"
abyss_stack_mcp_candidate_credential_name="abyss-stack-mcp-candidate-bearer-token"
abyss_stack_mcp_internal_effect_credential_name="abyss-stack-mcp-internal-effect-bearer-token"
abyss_stack_mcp_canary_signing_key_name="abyss-stack-mcp-canary-ed25519-private-key.pem"
abyss_stack_mcp_canary_public_key_name="abyss-stack-mcp-canary-ed25519-public-key.pem"
abyss_stack_mcp_auth_manifest_name="abyss-stack-mcp-auth-manifest.json"
abyss_stack_mcp_auth_manifest_path="${mcp_http_secret_dir}/${abyss_stack_mcp_auth_manifest_name}"
abyss_stack_mcp_service_root="${AOA_CONFIGS_ROOT}/mcp/services/abyss-stack-mcp"
abyss_stack_mcp_runtime_root="${AOA_STACK_ROOT}/Services/abyss-stack-mcp"
abyss_stack_mcp_venv="${abyss_stack_mcp_runtime_root}/venv"
abyss_stack_mcp_runtime_lock="${abyss_stack_mcp_runtime_root}/.runtime-provision.lock"
abyss_stack_mcp_operation_lock="${abyss_stack_mcp_runtime_root}/.runtime-operation.lock"
abyss_stack_mcp_read_rollback_grant="${abyss_stack_mcp_runtime_root}/.read-repair-rollback-grant"
abyss_stack_mcp_audit_root="${AOA_STACK_ROOT}/Logs/mcp/audit"
abyss_stack_mcp_read_audit_journal="${abyss_stack_mcp_audit_root}/policy-read.jsonl"
abyss_stack_mcp_candidate_audit_journal="${abyss_stack_mcp_audit_root}/policy-candidate.jsonl"
abyss_stack_mcp_effect_root="${AOA_STACK_ROOT}/Logs/mcp/internal-effects/read-restart-pilot"
abyss_stack_mcp_observation_root="${AOA_STACK_ROOT}/Logs/mcp/observations"
abyss_stack_mcp_observation_path="${abyss_stack_mcp_observation_root}/current.json"
abyss_stack_mcp_observation_overlay_path="${abyss_stack_mcp_observation_root}/evidence-overlay.json"
abyss_stack_mcp_admission_root="${AOA_STACK_ROOT}/Logs/mcp/admission"
abyss_stack_mcp_repair_fallback="${abyss_stack_mcp_admission_root}/runtime-repair-fallback.units"
abyss_stack_mcp_keeper_inbox_root="${abyss_stack_mcp_admission_root}/keeper-inbox"
abyss_stack_mcp_preflight_root="${AOA_STACK_ROOT}/Logs/mcp/preflight"
abyss_stack_mcp_protocol_watch_root="${AOA_STACK_ROOT}/Logs/mcp/protocol-watch"
abyss_stack_mcp_orchestration_root="${AOA_STACK_ROOT}/Logs/mcp/cross-organ-orchestrations"
abyss_stack_mcp_tasks_root="${AOA_STACK_ROOT}/Logs/mcp/tasks"
abyss_stack_mcp_read_tasks_root="${abyss_stack_mcp_tasks_root}/abyss-stack-read"
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

aoa_set_abyss_stack_mcp_auto_repair_policy() {
  local requested_state="$1"
  local marker="$abyss_stack_mcp_auto_repair_marker"
  local temp_path=""

  if [[ -e "$mcp_http_secret_dir" || -L "$mcp_http_secret_dir" ]]; then
    [[ -d "$mcp_http_secret_dir" && ! -L "$mcp_http_secret_dir" ]] || \
      aoa_die "MCP HTTP secret root must be a directory, not a symlink"
  elif [[ "$requested_state" == "enabled" ]]; then
    install -d -m 0700 "$mcp_http_secret_dir"
  else
    aoa_note "abyss-stack MCP automatic runtime repair is already disabled"
    return 0
  fi

  if [[ "$requested_state" == "enabled" ]]; then
    if [[ -e "$marker" || -L "$marker" ]]; then
      [[ -f "$marker" && ! -L "$marker" && "$(<"$marker")" == "enabled" ]] || \
        aoa_die "existing abyss-stack MCP auto-repair marker is unsafe or invalid"
      chmod 0600 "$marker"
      aoa_note "abyss-stack MCP automatic runtime repair is already enabled"
      return 0
    fi
    temp_path="$(mktemp "${mcp_http_secret_dir}/.abyss-stack-mcp-auto-repair.XXXXXX")"
    printf 'enabled\n' > "$temp_path"
    chmod 0600 "$temp_path"
    if ! ln -- "$temp_path" "$marker" 2>/dev/null; then
      rm -f -- "$temp_path"
      aoa_die "failed to atomically enable abyss-stack MCP automatic runtime repair"
    fi
    rm -f -- "$temp_path"
    aoa_note "enabled abyss-stack MCP automatic runtime repair"
    return 0
  fi

  if [[ ! -e "$marker" && ! -L "$marker" ]]; then
    aoa_note "abyss-stack MCP automatic runtime repair is already disabled"
    return 0
  fi
  [[ -f "$marker" && ! -L "$marker" && "$(<"$marker")" == "enabled" ]] || \
    aoa_die "existing abyss-stack MCP auto-repair marker is unsafe or invalid"
  rm -- "$marker"
  aoa_note "disabled abyss-stack MCP automatic runtime repair"
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

aoa_provision_ovms_auth() {
  local token=""
  local token_size=0
  local file_size=0
  local expected_json=""
  local installed_json=""

  command -v podman >/dev/null 2>&1 || aoa_die "podman is required to provision OVMS auth"
  [[ -f "$ovms_credential_path" && ! -L "$ovms_credential_path" ]] || \
    aoa_die "OVMS credential must be a regular non-symlink file: ${ovms_credential_path}"
  token="$(<"$ovms_credential_path")"
  token_size="${#token}"
  file_size="$(stat -c '%s' "$ovms_credential_path")"
  if [[ ! "$token" =~ ^[A-Za-z0-9._~-]{43,512}$ ]] || \
    ! ((file_size == token_size || file_size == token_size + 1)); then
    aoa_die "OVMS credential has invalid content: ${ovms_credential_path}"
  fi
  chmod 0600 "$ovms_credential_path"

  if podman secret inspect "$ovms_credential_name" >/dev/null 2>&1; then
    expected_json="$(
      aoa_run_isolated_python python3 -c \
        'import json, pathlib, sys; print(json.dumps(pathlib.Path(sys.argv[1]).read_text()))' \
        "$ovms_credential_path"
    )"
    installed_json="$(
      podman secret inspect --showsecret --format '{{json .SecretData}}' \
        "$ovms_credential_name"
    )"
    [[ "$installed_json" == "$expected_json" ]] || \
      aoa_die "OVMS credential differs from the installed Podman secret; stop its consumers before an explicit rotation"
    aoa_note "OVMS Podman secret already matches the canonical credential"
    return 0
  fi

  podman secret create \
    --label io.abyss.owner=abyss-stack \
    "$ovms_credential_name" "$ovms_credential_path" >/dev/null
  aoa_note "OVMS Podman secret provisioned from the canonical credential"
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

aoa_validate_abyss_stack_mcp_canary_signing_key() {
  local key_path="$1"

  [[ -f "$key_path" && ! -L "$key_path" ]] || \
    aoa_die "existing abyss-stack MCP canary signing key must be a regular non-symlink file"
  [[ "$(stat -c '%a' "$key_path")" == "600" ]] || \
    aoa_die "existing abyss-stack MCP canary signing key must have mode 0600"
  [[ "$(stat -c '%u' "$key_path")" == "$(id -u)" ]] || \
    aoa_die "existing abyss-stack MCP canary signing key must be owned by the current user"
  if ! openssl pkey -in "$key_path" -check -noout >/dev/null 2>&1; then
    aoa_die "existing abyss-stack MCP canary signing key must be a valid private key"
  fi
  if [[ "$(openssl pkey -in "$key_path" -text_pub -noout 2>/dev/null | head -n 1)" != "ED25519 Public-Key:" ]]; then
    aoa_die "existing abyss-stack MCP canary signing key must be Ed25519"
  fi
}

aoa_provision_abyss_stack_mcp_canary_signing_key() {
  local key_path="${mcp_http_secret_dir}/${abyss_stack_mcp_canary_signing_key_name}"
  local temp_path=""

  if [[ -e "$key_path" || -L "$key_path" ]]; then
    aoa_validate_abyss_stack_mcp_canary_signing_key "$key_path"
    aoa_note "abyss-stack MCP canary signing key already provisioned under the deployed Secrets root"
    return 0
  fi
  temp_path="$(mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_canary_signing_key_name}.XXXXXX")"
  chmod 0600 "$temp_path"
  if ! openssl genpkey -algorithm ED25519 -out "$temp_path" >/dev/null 2>&1; then
    rm -f -- "$temp_path"
    aoa_die "failed to generate the abyss-stack MCP canary signing key"
  fi
  aoa_validate_abyss_stack_mcp_canary_signing_key "$temp_path"
  if ln -- "$temp_path" "$key_path" 2>/dev/null; then
    rm -f -- "$temp_path"
    aoa_note "provisioned abyss-stack MCP canary signing key under the deployed Secrets root"
    return 0
  fi
  rm -f -- "$temp_path"
  if [[ ! -e "$key_path" && ! -L "$key_path" ]]; then
    aoa_die "failed to atomically provision the abyss-stack MCP canary signing key"
  fi
  aoa_validate_abyss_stack_mcp_canary_signing_key "$key_path"
  aoa_note "abyss-stack MCP canary signing key already provisioned under the deployed Secrets root"
}

aoa_validate_abyss_stack_mcp_canary_public_key() {
  local key_path="$1"

  [[ -f "$key_path" && ! -L "$key_path" ]] || \
    aoa_die "existing abyss-stack MCP canary public key must be a regular non-symlink file"
  [[ "$(stat -c '%a' "$key_path")" == "600" ]] || \
    aoa_die "existing abyss-stack MCP canary public key must have mode 0600"
  [[ "$(stat -c '%u' "$key_path")" == "$(id -u)" ]] || \
    aoa_die "existing abyss-stack MCP canary public key must be owned by the current user"
  if ! openssl pkey -pubin -in "$key_path" -pubout -out /dev/null 2>/dev/null; then
    aoa_die "existing abyss-stack MCP canary public key must be a valid public key"
  fi
  if [[ "$(openssl pkey -pubin -in "$key_path" -text_pub -noout 2>/dev/null | head -n 1)" != "ED25519 Public-Key:" ]]; then
    aoa_die "existing abyss-stack MCP canary public key must be Ed25519"
  fi
}

aoa_provision_abyss_stack_mcp_canary_public_key() {
  local private_path="${mcp_http_secret_dir}/${abyss_stack_mcp_canary_signing_key_name}"
  local public_path="${mcp_http_secret_dir}/${abyss_stack_mcp_canary_public_key_name}"
  local temp_path=""

  aoa_validate_abyss_stack_mcp_canary_signing_key "$private_path"
  temp_path="$(mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_canary_public_key_name}.XXXXXX")"
  chmod 0600 "$temp_path"
  if ! openssl pkey -in "$private_path" -pubout -out "$temp_path" >/dev/null 2>&1; then
    rm -f -- "$temp_path"
    aoa_die "failed to derive the abyss-stack MCP canary public key"
  fi
  aoa_validate_abyss_stack_mcp_canary_public_key "$temp_path"
  if [[ -e "$public_path" || -L "$public_path" ]]; then
    aoa_validate_abyss_stack_mcp_canary_public_key "$public_path"
    if ! cmp -s -- "$temp_path" "$public_path"; then
      rm -f -- "$temp_path"
      aoa_die "existing abyss-stack MCP canary public key conflicts with the signing key"
    fi
    rm -f -- "$temp_path"
    aoa_note "abyss-stack MCP canary public key already pinned under the deployed Secrets root"
    return 0
  fi
  if ln -- "$temp_path" "$public_path" 2>/dev/null; then
    rm -f -- "$temp_path"
    aoa_note "pinned abyss-stack MCP canary public key under the deployed Secrets root"
    return 0
  fi
  rm -f -- "$temp_path"
  if [[ ! -e "$public_path" && ! -L "$public_path" ]]; then
    aoa_die "failed to atomically pin the abyss-stack MCP canary public key"
  fi
  aoa_validate_abyss_stack_mcp_canary_public_key "$public_path"
  aoa_note "abyss-stack MCP canary public key already pinned under the deployed Secrets root"
}

aoa_provision_mcp_http_auth() {
  aoa_provision_mcp_bearer \
    "$mcp_http_credential_name" \
    "MCP HTTP bearer credential"
}

aoa_provision_organ_mcp_read_auth() {
  local decisions_path="${mcp_http_secret_dir}/${aoa_decisions_mcp_read_credential_name}"
  local memo_path="${mcp_http_secret_dir}/${aoa_memo_mcp_read_credential_name}"
  local evals_path="${mcp_http_secret_dir}/${aoa_evals_mcp_read_credential_name}"
  local kag_path="${mcp_http_secret_dir}/${aoa_kag_mcp_read_credential_name}"
  local connector_4pda_path="${mcp_http_secret_dir}/${aoa_4pda_connector_mcp_read_credential_name}"
  local connector_course_path="${mcp_http_secret_dir}/${aoa_course_connector_mcp_read_credential_name}"
  local connector_discord_path="${mcp_http_secret_dir}/${aoa_discord_connector_mcp_read_credential_name}"
  local session_memory_path="${mcp_http_secret_dir}/${aoa_session_memory_mcp_read_credential_name}"
  local connector_stackoverflow_path="${mcp_http_secret_dir}/${aoa_stackoverflow_connector_mcp_read_credential_name}"
  local stats_path="${mcp_http_secret_dir}/${aoa_stats_mcp_read_credential_name}"
  local connector_telegram_path="${mcp_http_secret_dir}/${aoa_telegram_connector_mcp_read_credential_name}"
  local connector_xda_path="${mcp_http_secret_dir}/${aoa_xda_connector_mcp_read_credential_name}"
  local machine_path="${mcp_http_secret_dir}/${abyss_machine_mcp_read_credential_name}"
  local tos_corpus_path="${mcp_http_secret_dir}/${tos_corpus_mcp_read_credential_name}"
  local decisions_token=""
  local memo_token=""
  local evals_token=""
  local kag_token=""
  local connector_4pda_token=""
  local connector_course_token=""
  local connector_discord_token=""
  local session_memory_token=""
  local connector_stackoverflow_token=""
  local stats_token=""
  local connector_telegram_token=""
  local connector_xda_token=""
  local machine_token=""
  local tos_corpus_token=""
  local decisions_digest=""
  local memo_digest=""
  local evals_digest=""
  local kag_digest=""
  local connector_4pda_digest=""
  local connector_course_digest=""
  local connector_discord_digest=""
  local session_memory_digest=""
  local connector_stackoverflow_digest=""
  local stats_digest=""
  local connector_telegram_digest=""
  local connector_xda_digest=""
  local machine_digest=""
  local tos_corpus_digest=""
  local manifest_temp=""

  aoa_provision_mcp_bearer \
    "$aoa_decisions_mcp_read_credential_name" \
    "aoa-decisions MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_memo_mcp_read_credential_name" \
    "aoa-memo MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_evals_mcp_read_credential_name" \
    "aoa-evals MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_kag_mcp_read_credential_name" \
    "aoa-kag MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_4pda_connector_mcp_read_credential_name" \
    "aoa-4pda-connector MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_course_connector_mcp_read_credential_name" \
    "aoa-course-connector MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_discord_connector_mcp_read_credential_name" \
    "aoa-discord-connector MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_session_memory_mcp_read_credential_name" \
    "aoa-session-memory MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_stackoverflow_connector_mcp_read_credential_name" \
    "aoa-stackoverflow-connector MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_stats_mcp_read_credential_name" \
    "aoa-stats MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_telegram_connector_mcp_read_credential_name" \
    "aoa-telegram-connector MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_xda_connector_mcp_read_credential_name" \
    "aoa-xda-connector MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$abyss_machine_mcp_read_credential_name" \
    "abyss-machine MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$tos_corpus_mcp_read_credential_name" \
    "tos-corpus MCP read bearer credential"

  decisions_token="$(<"$decisions_path")"
  memo_token="$(<"$memo_path")"
  evals_token="$(<"$evals_path")"
  kag_token="$(<"$kag_path")"
  connector_4pda_token="$(<"$connector_4pda_path")"
  connector_course_token="$(<"$connector_course_path")"
  connector_discord_token="$(<"$connector_discord_path")"
  session_memory_token="$(<"$session_memory_path")"
  connector_stackoverflow_token="$(<"$connector_stackoverflow_path")"
  stats_token="$(<"$stats_path")"
  connector_telegram_token="$(<"$connector_telegram_path")"
  connector_xda_token="$(<"$connector_xda_path")"
  machine_token="$(<"$machine_path")"
  tos_corpus_token="$(<"$tos_corpus_path")"
  [[ "$(printf '%s\n' \
      "$decisions_token" "$memo_token" "$evals_token" \
      "$kag_token" "$connector_4pda_token" "$connector_course_token" \
      "$connector_discord_token" "$session_memory_token" \
      "$connector_stackoverflow_token" "$stats_token" \
      "$connector_telegram_token" "$connector_xda_token" \
      "$machine_token" "$tos_corpus_token" \
      | sort -u | wc -l)" == "14" ]] || \
    aoa_die "organ MCP read bearer credentials must be owner-distinct"

  decisions_digest="$(
    printf '%s' "$decisions_token" | sha256sum | cut -d' ' -f1
  )"
  memo_digest="$(
    printf '%s' "$memo_token" | sha256sum | cut -d' ' -f1
  )"
  evals_digest="$(
    printf '%s' "$evals_token" | sha256sum | cut -d' ' -f1
  )"
  kag_digest="$(
    printf '%s' "$kag_token" | sha256sum | cut -d' ' -f1
  )"
  connector_4pda_digest="$(
    printf '%s' "$connector_4pda_token" | sha256sum | cut -d' ' -f1
  )"
  connector_course_digest="$(
    printf '%s' "$connector_course_token" | sha256sum | cut -d' ' -f1
  )"
  connector_discord_digest="$(
    printf '%s' "$connector_discord_token" | sha256sum | cut -d' ' -f1
  )"
  session_memory_digest="$(
    printf '%s' "$session_memory_token" | sha256sum | cut -d' ' -f1
  )"
  connector_stackoverflow_digest="$(
    printf '%s' "$connector_stackoverflow_token" | sha256sum | cut -d' ' -f1
  )"
  stats_digest="$(
    printf '%s' "$stats_token" | sha256sum | cut -d' ' -f1
  )"
  connector_telegram_digest="$(
    printf '%s' "$connector_telegram_token" | sha256sum | cut -d' ' -f1
  )"
  connector_xda_digest="$(
    printf '%s' "$connector_xda_token" | sha256sum | cut -d' ' -f1
  )"
  machine_digest="$(
    printf '%s' "$machine_token" | sha256sum | cut -d' ' -f1
  )"
  tos_corpus_digest="$(
    printf '%s' "$tos_corpus_token" | sha256sum | cut -d' ' -f1
  )"
  [[ "$decisions_digest" =~ ^[0-9a-f]{64}$ && \
     "$memo_digest" =~ ^[0-9a-f]{64}$ && \
     "$evals_digest" =~ ^[0-9a-f]{64}$ && \
     "$kag_digest" =~ ^[0-9a-f]{64}$ && \
     "$connector_4pda_digest" =~ ^[0-9a-f]{64}$ && \
     "$connector_course_digest" =~ ^[0-9a-f]{64}$ && \
     "$connector_discord_digest" =~ ^[0-9a-f]{64}$ && \
     "$session_memory_digest" =~ ^[0-9a-f]{64}$ && \
     "$connector_stackoverflow_digest" =~ ^[0-9a-f]{64}$ && \
     "$stats_digest" =~ ^[0-9a-f]{64}$ && \
     "$connector_telegram_digest" =~ ^[0-9a-f]{64}$ && \
     "$connector_xda_digest" =~ ^[0-9a-f]{64}$ && \
     "$machine_digest" =~ ^[0-9a-f]{64}$ && \
     "$tos_corpus_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "failed to bind organ MCP read credential digests"

  if [[ -e "$organ_mcp_read_auth_manifest_path" || \
        -L "$organ_mcp_read_auth_manifest_path" ]]; then
    [[ -f "$organ_mcp_read_auth_manifest_path" && \
       ! -L "$organ_mcp_read_auth_manifest_path" ]] || \
      aoa_die "existing organ MCP read auth manifest must be a regular non-symlink file"
  fi
  manifest_temp="$(
    mktemp "${mcp_http_secret_dir}/.${organ_mcp_read_auth_manifest_name}.XXXXXX"
  )"
  chmod 0600 "$manifest_temp"
  if ! printf \
      '{"credentials":{"abyss-machine":{"policy_family":"read","sha256":"%s"},"aoa-4pda-connector":{"policy_family":"read","sha256":"%s"},"aoa-course-connector":{"policy_family":"read","sha256":"%s"},"aoa-decisions":{"policy_family":"read","sha256":"%s"},"aoa-discord-connector":{"policy_family":"read","sha256":"%s"},"aoa-evals":{"policy_family":"read","sha256":"%s"},"aoa-kag":{"policy_family":"read","sha256":"%s"},"aoa-memo":{"policy_family":"read","sha256":"%s"},"aoa-session-memory":{"policy_family":"read","sha256":"%s"},"aoa-stackoverflow-connector":{"policy_family":"read","sha256":"%s"},"aoa-stats":{"policy_family":"read","sha256":"%s"},"aoa-telegram-connector":{"policy_family":"read","sha256":"%s"},"aoa-xda-connector":{"policy_family":"read","sha256":"%s"},"tos-corpus":{"policy_family":"read","sha256":"%s"}},"schema_version":"organ_mcp_read_auth_manifest_v1"}\n' \
      "$machine_digest" \
      "$connector_4pda_digest" \
      "$connector_course_digest" \
      "$decisions_digest" \
      "$connector_discord_digest" \
      "$evals_digest" \
      "$kag_digest" \
      "$memo_digest" \
      "$session_memory_digest" \
      "$connector_stackoverflow_digest" \
      "$stats_digest" \
      "$connector_telegram_digest" \
      "$connector_xda_digest" \
      "$tos_corpus_digest" > "$manifest_temp"; then
    rm -f -- "$manifest_temp"
    aoa_die "failed to stage the organ MCP read auth manifest"
  fi
  if ! mv -f -- "$manifest_temp" "$organ_mcp_read_auth_manifest_path"; then
    rm -f -- "$manifest_temp"
    aoa_die "failed to publish the organ MCP read auth manifest"
  fi
  chmod 0600 "$organ_mcp_read_auth_manifest_path"
  aoa_note "refreshed owner-distinct organ MCP read credential manifest"
}

aoa_provision_organ_mcp_candidate_auth() {
  local memo_candidate_path="${mcp_http_secret_dir}/${aoa_memo_mcp_candidate_credential_name}"
  local evals_candidate_path="${mcp_http_secret_dir}/${aoa_evals_mcp_candidate_credential_name}"
  local memo_candidate_token=""
  local evals_candidate_token=""
  local memo_candidate_digest=""
  local evals_candidate_digest=""
  local manifest_temp=""
  local credential_name=""
  local all_tokens=""

  aoa_provision_organ_mcp_read_auth
  aoa_provision_mcp_bearer \
    "$aoa_memo_mcp_candidate_credential_name" \
    "aoa-memo MCP candidate bearer credential"
  aoa_provision_mcp_bearer \
    "$aoa_evals_mcp_candidate_credential_name" \
    "aoa-evals MCP candidate bearer credential"

  memo_candidate_token="$(<"$memo_candidate_path")"
  evals_candidate_token="$(<"$evals_candidate_path")"
  for credential_name in \
    "$aoa_decisions_mcp_read_credential_name" \
    "$aoa_memo_mcp_read_credential_name" \
    "$aoa_evals_mcp_read_credential_name" \
    "$aoa_kag_mcp_read_credential_name" \
    "$aoa_4pda_connector_mcp_read_credential_name" \
    "$aoa_course_connector_mcp_read_credential_name" \
    "$aoa_discord_connector_mcp_read_credential_name" \
    "$aoa_session_memory_mcp_read_credential_name" \
    "$aoa_stackoverflow_connector_mcp_read_credential_name" \
    "$aoa_stats_mcp_read_credential_name" \
    "$aoa_telegram_connector_mcp_read_credential_name" \
    "$aoa_xda_connector_mcp_read_credential_name" \
    "$abyss_machine_mcp_read_credential_name" \
    "$tos_corpus_mcp_read_credential_name"; do
    all_tokens+="$(<"${mcp_http_secret_dir}/${credential_name}")"$'\n'
  done
  all_tokens+="${memo_candidate_token}"$'\n'"${evals_candidate_token}"$'\n'
  [[ "$(printf '%s' "$all_tokens" | sed '/^$/d' | sort -u | wc -l)" == "16" ]] || \
    aoa_die "organ MCP read and candidate bearer credentials must be contour-distinct"

  memo_candidate_digest="$(
    printf '%s' "$memo_candidate_token" | sha256sum | cut -d' ' -f1
  )"
  evals_candidate_digest="$(
    printf '%s' "$evals_candidate_token" | sha256sum | cut -d' ' -f1
  )"
  [[ "$memo_candidate_digest" =~ ^[0-9a-f]{64}$ && \
     "$evals_candidate_digest" =~ ^[0-9a-f]{64}$ && \
     "$memo_candidate_digest" != "$evals_candidate_digest" ]] || \
    aoa_die "failed to bind organ MCP candidate credential digests"

  if [[ -e "$organ_mcp_candidate_auth_manifest_path" || \
        -L "$organ_mcp_candidate_auth_manifest_path" ]]; then
    [[ -f "$organ_mcp_candidate_auth_manifest_path" && \
       ! -L "$organ_mcp_candidate_auth_manifest_path" ]] || \
      aoa_die "existing organ MCP candidate auth manifest must be a regular non-symlink file"
  fi
  manifest_temp="$(
    mktemp "${mcp_http_secret_dir}/.${organ_mcp_candidate_auth_manifest_name}.XXXXXX"
  )"
  chmod 0600 "$manifest_temp"
  if ! printf \
      '{"credentials":{"aoa-evals":{"policy_family":"candidate","sha256":"%s"},"aoa-memo":{"policy_family":"candidate","sha256":"%s"}},"schema_version":"organ_mcp_candidate_auth_manifest_v1"}\n' \
      "$evals_candidate_digest" \
      "$memo_candidate_digest" > "$manifest_temp"; then
    rm -f -- "$manifest_temp"
    aoa_die "failed to stage the organ MCP candidate auth manifest"
  fi
  if ! mv -f -- "$manifest_temp" "$organ_mcp_candidate_auth_manifest_path"; then
    rm -f -- "$manifest_temp"
    aoa_die "failed to publish the organ MCP candidate auth manifest"
  fi
  chmod 0600 "$organ_mcp_candidate_auth_manifest_path"
  aoa_note "refreshed contour-distinct organ MCP candidate credential manifest"
}

aoa_provision_abyss_stack_mcp_auth() {
  local read_path="${mcp_http_secret_dir}/${abyss_stack_mcp_read_credential_name}"
  local candidate_path="${mcp_http_secret_dir}/${abyss_stack_mcp_candidate_credential_name}"
  local effect_path="${mcp_http_secret_dir}/${abyss_stack_mcp_internal_effect_credential_name}"
  local read_token=""
  local candidate_token=""
  local effect_token=""
  local read_digest=""
  local candidate_digest=""
  local effect_digest=""
  local manifest_temp=""

  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_read_credential_name" \
    "abyss-stack MCP read bearer credential"
  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_candidate_credential_name" \
    "abyss-stack MCP candidate bearer credential"
  aoa_provision_mcp_bearer \
    "$abyss_stack_mcp_internal_effect_credential_name" \
    "abyss-stack MCP internal-effect bearer credential"
  aoa_provision_abyss_stack_mcp_canary_signing_key
  aoa_provision_abyss_stack_mcp_canary_public_key
  read_token="$(<"$read_path")"
  candidate_token="$(<"$candidate_path")"
  effect_token="$(<"$effect_path")"
  [[ "$read_token" != "$candidate_token" && \
     "$read_token" != "$effect_token" && \
     "$candidate_token" != "$effect_token" ]] || \
    aoa_die "abyss-stack MCP read, candidate, and internal-effect bearer credentials must be distinct"
  read_digest="$(
    printf '%s' "$read_token" | sha256sum | cut -d' ' -f1
  )"
  candidate_digest="$(
    printf '%s' "$candidate_token" | sha256sum | cut -d' ' -f1
  )"
  effect_digest="$(
    printf '%s' "$effect_token" | sha256sum | cut -d' ' -f1
  )"
  [[ "$read_digest" =~ ^[0-9a-f]{64}$ && \
     "$candidate_digest" =~ ^[0-9a-f]{64}$ && \
     "$effect_digest" =~ ^[0-9a-f]{64}$ && \
     "$read_digest" != "$candidate_digest" && \
     "$read_digest" != "$effect_digest" && \
     "$candidate_digest" != "$effect_digest" ]] || \
    aoa_die "failed to bind distinct abyss-stack MCP credentials"
  if [[ -e "$abyss_stack_mcp_auth_manifest_path" || \
        -L "$abyss_stack_mcp_auth_manifest_path" ]]; then
    [[ -f "$abyss_stack_mcp_auth_manifest_path" && \
       ! -L "$abyss_stack_mcp_auth_manifest_path" ]] || \
      aoa_die "existing abyss-stack MCP auth manifest must be a regular non-symlink file"
  fi
  manifest_temp="$(
    mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_auth_manifest_name}.XXXXXX"
  )"
  chmod 0600 "$manifest_temp"
  if ! printf \
      '{"candidate_sha256":"%s","internal_effect_sha256":"%s","read_sha256":"%s","schema_version":"abyss_stack_mcp_auth_manifest_v2"}\n' \
      "$candidate_digest" "$effect_digest" "$read_digest" > "$manifest_temp"; then
    rm -f -- "$manifest_temp"
    aoa_die "failed to stage the abyss-stack MCP auth manifest"
  fi
  if ! mv -f -- "$manifest_temp" "$abyss_stack_mcp_auth_manifest_path"; then
    rm -f -- "$manifest_temp"
    aoa_die "failed to publish the abyss-stack MCP auth manifest"
  fi
  chmod 0600 "$abyss_stack_mcp_auth_manifest_path"
  aoa_note "refreshed abyss-stack MCP credential separation manifest"
}

aoa_validate_abyss_stack_mcp_audit_journal() {
  local journal_path="$1"
  local journal_label="$2"
  local journal_size=""

  [[ -f "$journal_path" && ! -L "$journal_path" ]] || \
    aoa_die "${journal_label} must be a regular non-symlink file"
  [[ "$(stat -c '%a' "$journal_path")" == "600" ]] || \
    aoa_die "${journal_label} must have mode 0600"
  journal_size="$(stat -c '%s' "$journal_path")"
  [[ "$journal_size" =~ ^[0-9]+$ ]] || \
    aoa_die "${journal_label} size is invalid"
  ((journal_size <= 33554432)) || \
    aoa_die "${journal_label} exceeds the managed 32 MiB capacity"
}

aoa_verify_abyss_stack_mcp_audit_journals() {
  local contour="${1:-all}"

  case "$contour" in
    all)
      [[ -d "$abyss_stack_mcp_audit_root" && \
         ! -L "$abyss_stack_mcp_audit_root" ]] || \
        aoa_die "abyss-stack MCP audit root must be a non-symlink directory"
      [[ "$(stat -c '%a' "$abyss_stack_mcp_audit_root")" == "700" ]] || \
        aoa_die "abyss-stack MCP audit root must have mode 0700"
      aoa_validate_abyss_stack_mcp_audit_journal \
        "$abyss_stack_mcp_read_audit_journal" \
        "abyss-stack MCP read audit journal"
      aoa_validate_abyss_stack_mcp_audit_journal \
        "$abyss_stack_mcp_candidate_audit_journal" \
        "abyss-stack MCP candidate audit journal"
      [[ -d "$abyss_stack_mcp_effect_root" && \
         ! -L "$abyss_stack_mcp_effect_root" && \
         "$(stat -c '%a' "$abyss_stack_mcp_effect_root")" == "700" ]] || \
        aoa_die "abyss-stack MCP internal-effect root must be a mode-0700 non-symlink directory"
      ;;
    read)
      [[ -d "$abyss_stack_mcp_audit_root" && \
         ! -L "$abyss_stack_mcp_audit_root" ]] || \
        aoa_die "abyss-stack MCP audit root must be a non-symlink directory"
      [[ "$(stat -c '%a' "$abyss_stack_mcp_audit_root")" == "700" ]] || \
        aoa_die "abyss-stack MCP audit root must have mode 0700"
      aoa_validate_abyss_stack_mcp_audit_journal \
        "$abyss_stack_mcp_read_audit_journal" \
        "abyss-stack MCP read audit journal"
      ;;
    candidate)
      [[ -d "$abyss_stack_mcp_audit_root" && \
         ! -L "$abyss_stack_mcp_audit_root" ]] || \
        aoa_die "abyss-stack MCP audit root must be a non-symlink directory"
      [[ "$(stat -c '%a' "$abyss_stack_mcp_audit_root")" == "700" ]] || \
        aoa_die "abyss-stack MCP audit root must have mode 0700"
      aoa_validate_abyss_stack_mcp_audit_journal \
        "$abyss_stack_mcp_candidate_audit_journal" \
        "abyss-stack MCP candidate audit journal"
      ;;
    internal_effect)
      [[ -d "$abyss_stack_mcp_effect_root" && \
         ! -L "$abyss_stack_mcp_effect_root" ]] || \
        aoa_die "abyss-stack MCP internal-effect root must be a non-symlink directory"
      [[ "$(stat -c '%a' "$abyss_stack_mcp_effect_root")" == "700" ]] || \
        aoa_die "abyss-stack MCP internal-effect root must have mode 0700"
      ;;
    *)
      aoa_die "unknown abyss-stack MCP audit contour: ${contour}"
      ;;
  esac
}

aoa_provision_abyss_stack_mcp_audit_journals() {
  local parent=""
  local journal_path=""

  [[ -d "$AOA_STACK_ROOT" && ! -L "$AOA_STACK_ROOT" ]] || \
    aoa_die "abyss-stack runtime root must be a non-symlink directory"
  for parent in \
    "${AOA_STACK_ROOT}/Logs" \
    "${AOA_STACK_ROOT}/Logs/mcp"; do
    if [[ -e "$parent" || -L "$parent" ]]; then
      [[ -d "$parent" && ! -L "$parent" ]] || \
        aoa_die "abyss-stack MCP audit parent must be a non-symlink directory"
    else
      install -d -m 0750 "$parent"
    fi
  done
  if [[ -e "$abyss_stack_mcp_audit_root" || \
        -L "$abyss_stack_mcp_audit_root" ]]; then
    [[ -d "$abyss_stack_mcp_audit_root" && \
       ! -L "$abyss_stack_mcp_audit_root" ]] || \
      aoa_die "abyss-stack MCP audit root must be a non-symlink directory"
  else
    install -d -m 0700 "$abyss_stack_mcp_audit_root"
  fi
  chmod 0700 "$abyss_stack_mcp_audit_root"

  for journal_path in \
    "$abyss_stack_mcp_read_audit_journal" \
    "$abyss_stack_mcp_candidate_audit_journal"; do
    if [[ -e "$journal_path" || -L "$journal_path" ]]; then
      [[ -f "$journal_path" && ! -L "$journal_path" ]] || \
        aoa_die "existing abyss-stack MCP audit journal must be a regular non-symlink file"
    else
      (
        umask 077
        set -o noclobber
        : > "$journal_path"
      ) 2>/dev/null || true
      [[ -f "$journal_path" && ! -L "$journal_path" ]] || \
        aoa_die "failed to create an abyss-stack MCP audit journal"
    fi
    chmod 0600 "$journal_path"
  done
  aoa_verify_abyss_stack_mcp_audit_journals read
  aoa_verify_abyss_stack_mcp_audit_journals candidate
}

aoa_provision_abyss_stack_mcp_observation_root() {
  local parent=""

  [[ -d "$AOA_STACK_ROOT" && ! -L "$AOA_STACK_ROOT" ]] || \
    aoa_die "abyss-stack runtime root must be a non-symlink directory"
  for parent in \
    "${AOA_STACK_ROOT}/Logs" \
    "${AOA_STACK_ROOT}/Logs/mcp"; do
    if [[ -e "$parent" || -L "$parent" ]]; then
      [[ -d "$parent" && ! -L "$parent" ]] || \
        aoa_die "abyss-stack MCP observation parent must be a non-symlink directory"
    else
      install -d -m 0750 "$parent"
    fi
  done
  if [[ -e "$abyss_stack_mcp_observation_root" || \
        -L "$abyss_stack_mcp_observation_root" ]]; then
    [[ -d "$abyss_stack_mcp_observation_root" && \
       ! -L "$abyss_stack_mcp_observation_root" ]] || \
      aoa_die "abyss-stack MCP observation root must be a non-symlink directory"
  else
    install -d -m 0700 "$abyss_stack_mcp_observation_root"
  fi
  chmod 0700 "$abyss_stack_mcp_observation_root"
  for parent in \
    "$abyss_stack_mcp_observation_path" \
    "$abyss_stack_mcp_observation_overlay_path"; do
    if [[ -e "$parent" || -L "$parent" ]]; then
      [[ -f "$parent" && ! -L "$parent" ]] || \
        aoa_die "abyss-stack MCP observation files must be regular non-symlink files"
    fi
  done
}

aoa_provision_abyss_stack_mcp_admission_roots() {
  local target=""

  for target in \
    "$abyss_stack_mcp_admission_root" \
    "$abyss_stack_mcp_keeper_inbox_root" \
    "$abyss_stack_mcp_preflight_root" \
    "$abyss_stack_mcp_protocol_watch_root"; do
    if [[ -e "$target" || -L "$target" ]]; then
      [[ -d "$target" && ! -L "$target" ]] || \
        aoa_die "abyss-stack MCP admission runtime root must be a non-symlink directory"
    else
      install -d -m 0700 "$target"
    fi
    chmod 0700 "$target"
  done
}

aoa_provision_abyss_stack_mcp_orchestration_root() {
  local parent=""

  [[ -d "$AOA_STACK_ROOT" && ! -L "$AOA_STACK_ROOT" ]] || \
    aoa_die "abyss-stack runtime root must be a non-symlink directory"
  for parent in \
    "${AOA_STACK_ROOT}/Logs" \
    "${AOA_STACK_ROOT}/Logs/mcp"; do
    if [[ -e "$parent" || -L "$parent" ]]; then
      [[ -d "$parent" && ! -L "$parent" ]] || \
        aoa_die "cross-organ orchestration parent must be a non-symlink directory"
    else
      install -d -m 0750 "$parent"
    fi
  done
  if [[ -e "$abyss_stack_mcp_orchestration_root" || \
        -L "$abyss_stack_mcp_orchestration_root" ]]; then
    [[ -d "$abyss_stack_mcp_orchestration_root" && \
       ! -L "$abyss_stack_mcp_orchestration_root" ]] || \
      aoa_die "cross-organ orchestration root must be a non-symlink directory"
  else
    install -d -m 0700 "$abyss_stack_mcp_orchestration_root"
  fi
  chmod 0700 "$abyss_stack_mcp_orchestration_root"
}

aoa_provision_abyss_stack_mcp_tasks_root() {
  local target=""

  for target in \
    "$abyss_stack_mcp_tasks_root" \
    "$abyss_stack_mcp_read_tasks_root"; do
    if [[ -e "$target" || -L "$target" ]]; then
      [[ -d "$target" && ! -L "$target" ]] || \
        aoa_die "abyss-stack MCP Tasks root must be a non-symlink directory"
    else
      install -d -m 0700 "$target"
    fi
    chmod 0700 "$target"
  done
}

aoa_provision_abyss_stack_mcp_effect_root() {
  local parent=""

  for parent in \
    "${AOA_STACK_ROOT}/Logs" \
    "${AOA_STACK_ROOT}/Logs/mcp" \
    "${AOA_STACK_ROOT}/Logs/mcp/internal-effects" \
    "$abyss_stack_mcp_effect_root"; do
    if [[ -e "$parent" || -L "$parent" ]]; then
      [[ -d "$parent" && ! -L "$parent" ]] || \
        aoa_die "abyss-stack MCP effect root must use non-symlink directories"
    else
      install -d -m 0700 "$parent"
    fi
    chmod 0700 "$parent"
  done
}

aoa_require_abyss_stack_mcp_units_stopped_for_rotation() {
  local unit=""
  local active_state=""

  for unit in \
    abyss-stack-mcp-read.service \
    abyss-stack-mcp-read-bootstrap.service \
    abyss-stack-mcp-read-fallback.service \
    abyss-stack-mcp-candidate.service \
    abyss-stack-mcp-internal-effect.service; do
    if ! active_state="$(
      systemctl --user show \
        --property=ActiveState \
        --value \
        "$unit" 2>/dev/null
    )"; then
      aoa_die "cannot observe ${unit}; refusing credential rotation"
    fi
    case "$active_state" in
      inactive|failed)
        ;;
      *)
        aoa_die "refusing credential rotation while ${unit} is ${active_state:-unknown}"
        ;;
    esac
  done
}

aoa_rotate_abyss_stack_mcp_auth() {
  local read_path="${mcp_http_secret_dir}/${abyss_stack_mcp_read_credential_name}"
  local candidate_path="${mcp_http_secret_dir}/${abyss_stack_mcp_candidate_credential_name}"
  local effect_path="${mcp_http_secret_dir}/${abyss_stack_mcp_internal_effect_credential_name}"
  local read_temp=""
  local candidate_temp=""
  local effect_temp=""
  local manifest_temp=""
  local read_token=""
  local candidate_token=""
  local effect_token=""
  local read_digest=""
  local candidate_digest=""
  local effect_digest=""

  aoa_require_abyss_stack_mcp_units_stopped_for_rotation
  aoa_provision_abyss_stack_mcp_auth
  read_temp="$(
    mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_read_credential_name}.rotate.XXXXXX"
  )"
  candidate_temp="$(
    mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_candidate_credential_name}.rotate.XXXXXX"
  )"
  effect_temp="$(
    mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_internal_effect_credential_name}.rotate.XXXXXX"
  )"
  manifest_temp="$(
    mktemp "${mcp_http_secret_dir}/.${abyss_stack_mcp_auth_manifest_name}.rotate.XXXXXX"
  )"
  if ! aoa_run_isolated_python python3 \
      -c 'import secrets; print(secrets.token_urlsafe(48))' > "$read_temp" || \
     ! aoa_run_isolated_python python3 \
      -c 'import secrets; print(secrets.token_urlsafe(48))' > "$candidate_temp" || \
     ! aoa_run_isolated_python python3 \
      -c 'import secrets; print(secrets.token_urlsafe(48))' > "$effect_temp"; then
    rm -f -- "$read_temp" "$candidate_temp" "$effect_temp" "$manifest_temp"
    aoa_die "failed to generate rotated abyss-stack MCP credentials"
  fi
  chmod 0600 "$read_temp" "$candidate_temp" "$effect_temp" "$manifest_temp"
  aoa_validate_mcp_bearer_file \
    "$read_temp" \
    "rotated abyss-stack MCP read bearer credential"
  aoa_validate_mcp_bearer_file \
    "$candidate_temp" \
    "rotated abyss-stack MCP candidate bearer credential"
  aoa_validate_mcp_bearer_file \
    "$effect_temp" \
    "rotated abyss-stack MCP internal-effect bearer credential"
  read_token="$(<"$read_temp")"
  candidate_token="$(<"$candidate_temp")"
  effect_token="$(<"$effect_temp")"
  [[ "$read_token" != "$candidate_token" && \
     "$read_token" != "$effect_token" && \
     "$candidate_token" != "$effect_token" ]] || {
    rm -f -- "$read_temp" "$candidate_temp" "$effect_temp" "$manifest_temp"
    aoa_die "rotated abyss-stack MCP credentials must be distinct"
  }
  read_digest="$(
    printf '%s' "$read_token" | sha256sum | cut -d' ' -f1
  )"
  candidate_digest="$(
    printf '%s' "$candidate_token" | sha256sum | cut -d' ' -f1
  )"
  effect_digest="$(
    printf '%s' "$effect_token" | sha256sum | cut -d' ' -f1
  )"
  if ! printf \
      '{"candidate_sha256":"%s","internal_effect_sha256":"%s","read_sha256":"%s","schema_version":"abyss_stack_mcp_auth_manifest_v2"}\n' \
      "$candidate_digest" "$effect_digest" "$read_digest" > "$manifest_temp"; then
    rm -f -- "$read_temp" "$candidate_temp" "$effect_temp" "$manifest_temp"
    aoa_die "failed to stage the rotated abyss-stack MCP auth manifest"
  fi
  if ! mv -f -- "$read_temp" "$read_path"; then
    rm -f -- "$read_temp" "$candidate_temp" "$effect_temp" "$manifest_temp"
    aoa_die "failed to publish the rotated abyss-stack MCP read credential"
  fi
  if ! mv -f -- "$candidate_temp" "$candidate_path"; then
    rm -f -- "$candidate_temp" "$effect_temp" "$manifest_temp"
    aoa_die "credential rotation stopped in a fail-closed partial state"
  fi
  if ! mv -f -- "$effect_temp" "$effect_path"; then
    rm -f -- "$effect_temp" "$manifest_temp"
    aoa_die "credential rotation stopped in a fail-closed partial state"
  fi
  if ! mv -f -- "$manifest_temp" "$abyss_stack_mcp_auth_manifest_path"; then
    rm -f -- "$manifest_temp"
    aoa_die "credential rotation stopped before manifest publication"
  fi
  chmod 0600 \
    "$read_path" \
    "$candidate_path" \
    "$effect_path" \
    "$abyss_stack_mcp_auth_manifest_path"
  aoa_note "rotated all three abyss-stack MCP credentials and their digest manifest"
  aoa_note "managed units remain stopped; refresh consumers before a canary start"
}

aoa_require_abyss_stack_mcp_units_stopped() {
  local allow_active_read_units="${1:-0}"
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
  local unit_contour=""

  abyss_stack_mcp_units_error=""
  for unit in \
    abyss-stack-mcp-read.service \
    abyss-stack-mcp-read-bootstrap.service \
    abyss-stack-mcp-read-fallback.service \
    abyss-stack-mcp-candidate.service \
    abyss-stack-mcp-internal-effect.service; do
    unit_contour="${unit#abyss-stack-mcp-}"
    unit_contour="${unit_contour%.service}"
    if [[ "$unit_contour" == "internal-effect" ]]; then
      unit_contour="internal_effect"
    elif [[ "$unit_contour" == "read-bootstrap" || \
            "$unit_contour" == "read-fallback" ]]; then
      unit_contour="read"
    fi
    expected_unit_source="${AOA_CONFIGS_ROOT}/systemd/user/${unit}"
    expected_unit_target="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user/${unit}"
    expected_exec_start="/usr/bin/flock --shared --no-fork ${abyss_stack_mcp_source_lock} /usr/bin/flock --shared --no-fork ${abyss_stack_mcp_runtime_lock} /usr/bin/env ${AOA_CONFIGS_ROOT}/scripts/aoa-install-systemd --launch-verified-abyss-stack-mcp=${unit_contour}"
    if [[ "$unit_contour" == "candidate" || \
          "$unit_contour" == "internal_effect" ]]; then
      expected_exec_start="/usr/bin/flock --shared --no-fork ${abyss_stack_mcp_operation_lock} ${expected_exec_start}"
    fi
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
      active)
        if [[ "$allow_active_read_units" -eq 1 && \
              ("$unit" == "abyss-stack-mcp-read.service" || \
               "$unit" == "abyss-stack-mcp-read-bootstrap.service" || \
               "$unit" == "abyss-stack-mcp-read-fallback.service") ]]; then
          continue
        fi
        abyss_stack_mcp_units_error="refusing to replace abyss-stack MCP runtime while ${unit} is ${unit_state}"
        return 1
        ;;
      activating|reloading|deactivating)
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

aoa_verify_abyss_stack_mcp_repair_paths() {
  local target=""

  [[ -d "$AOA_STACK_ROOT" && ! -L "$AOA_STACK_ROOT" ]] || \
    aoa_die "abyss-stack runtime root must be a non-symlink directory"
  for target in \
    "${AOA_STACK_ROOT}/Logs" \
    "${AOA_STACK_ROOT}/Logs/mcp" \
    "${AOA_STACK_ROOT}/Logs/mcp/internal-effects" \
    "$abyss_stack_mcp_runtime_root" \
    "$abyss_stack_mcp_source_lock_root" \
    "$abyss_stack_mcp_observation_root" \
    "$abyss_stack_mcp_admission_root" \
    "$abyss_stack_mcp_keeper_inbox_root" \
    "$abyss_stack_mcp_preflight_root" \
    "$abyss_stack_mcp_protocol_watch_root" \
    "$abyss_stack_mcp_orchestration_root" \
    "$abyss_stack_mcp_tasks_root" \
    "$abyss_stack_mcp_read_tasks_root" \
    "$abyss_stack_mcp_effect_root"; do
    if [[ -e "$target" || -L "$target" ]]; then
      [[ -d "$target" && ! -L "$target" ]] || \
        aoa_die "repair-managed abyss-stack MCP runtime path must be a non-symlink directory: ${target}"
    fi
  done
  for target in \
    "$abyss_stack_mcp_observation_path" \
    "$abyss_stack_mcp_observation_overlay_path"; do
    if [[ -e "$target" || -L "$target" ]]; then
      [[ -f "$target" && ! -L "$target" ]] || \
        aoa_die "repair-managed abyss-stack MCP observation path must be a regular non-symlink file: ${target}"
    fi
  done
  if [[ -e "$abyss_stack_mcp_venv" || -L "$abyss_stack_mcp_venv" ]]; then
    [[ -d "$abyss_stack_mcp_venv" && ! -L "$abyss_stack_mcp_venv" ]] || \
      aoa_die "existing abyss-stack MCP runtime must be a non-symlink directory"
  fi
  if [[ -e "$abyss_stack_mcp_read_rollback_grant" || \
        -L "$abyss_stack_mcp_read_rollback_grant" ]]; then
    [[ -f "$abyss_stack_mcp_read_rollback_grant" && \
       ! -L "$abyss_stack_mcp_read_rollback_grant" ]] || \
      aoa_die "abyss-stack MCP read rollback grant must be a regular non-symlink file"
    [[ "$(stat -c '%a' "$abyss_stack_mcp_read_rollback_grant")" == "600" ]] || \
      aoa_die "abyss-stack MCP read rollback grant must use mode 0600"
  fi
}

aoa_verify_abyss_stack_mcp_repair_eligibility() {
  local lock_path="${abyss_stack_mcp_service_root}/requirements.lock"
  local resolved_bootstrap_python=""
  local operation_lock_fd=""
  local source_lock_fd=""
  local runtime_lock_fd=""

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
  [[ -f "$abyss_stack_mcp_source_lock" && \
     ! -L "$abyss_stack_mcp_source_lock" ]] || \
    aoa_die "abyss-stack MCP source projection lock is unavailable"
  [[ -f "$abyss_stack_mcp_runtime_lock" && \
     ! -L "$abyss_stack_mcp_runtime_lock" ]] || \
    aoa_die "abyss-stack MCP runtime lock is unavailable"
  if [[ -e "$abyss_stack_mcp_operation_lock" || \
        -L "$abyss_stack_mcp_operation_lock" ]]; then
    [[ -f "$abyss_stack_mcp_operation_lock" && \
       ! -L "$abyss_stack_mcp_operation_lock" ]] || \
      aoa_die "abyss-stack MCP operation lock must be a regular non-symlink file"
    exec {operation_lock_fd}< "$abyss_stack_mcp_operation_lock"
    if ! /usr/bin/flock --exclusive --nonblock "$operation_lock_fd"; then
      aoa_die "another provisioner or a managed non-read abyss-stack MCP plane holds the operation lock"
    fi
  fi
  exec {source_lock_fd}< "$abyss_stack_mcp_source_lock"
  if ! /usr/bin/flock --shared --nonblock "$source_lock_fd"; then
    aoa_die "Configs sync or runtime provisioning holds the abyss-stack MCP source projection lock"
  fi
  exec {runtime_lock_fd}< "$abyss_stack_mcp_runtime_lock"
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
  aoa_verify_abyss_stack_mcp_repair_paths
  aoa_verify_abyss_stack_mcp_audit_journals all
  if ! aoa_require_abyss_stack_mcp_units_stopped 1; then
    aoa_die "$abyss_stack_mcp_units_error"
  fi
  exec {runtime_lock_fd}>&-
  exec {source_lock_fd}>&-
  if [[ -n "$operation_lock_fd" ]]; then
    exec {operation_lock_fd}>&-
  fi
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

aoa_verify_abyss_stack_mcp_runtime_imports() {
  PYTHONDONTWRITEBYTECODE=1 \
    aoa_run_isolated_python "${abyss_stack_mcp_venv}/bin/python" -c \
      'import encodings, importlib.metadata, ssl; import abyss_stack_mcp, aoa_sdk, mcp, pydantic; assert importlib.metadata.version("aoa-sdk") == "0.10.2"'
}

aoa_verify_abyss_stack_mcp_read_rollback_grant() {
  local recorded_identity="$1"
  local observed_content_digest="$2"
  local grant=""

  [[ -f "$abyss_stack_mcp_read_rollback_grant" && \
     ! -L "$abyss_stack_mcp_read_rollback_grant" ]] || return 1
  [[ "$(stat -c '%a' "$abyss_stack_mcp_read_rollback_grant")" == "600" ]] || \
    return 1
  grant="$(<"$abyss_stack_mcp_read_rollback_grant")"
  [[ "$grant" =~ ^[0-9a-f]{64}:[0-9a-f]{64}:[0-9a-f]{64}$ ]] || \
    return 1
  [[ "$grant" == "${observed_content_digest}:${recorded_identity}" ]]
}

aoa_provision_abyss_stack_mcp_unit_operation_lock() {
  if [[ -e "$abyss_stack_mcp_runtime_root" || \
        -L "$abyss_stack_mcp_runtime_root" ]]; then
    [[ -d "$abyss_stack_mcp_runtime_root" && \
       ! -L "$abyss_stack_mcp_runtime_root" ]] || \
      aoa_die "abyss-stack MCP runtime root must be a non-symlink directory"
  else
    install -d -m 0750 "$abyss_stack_mcp_runtime_root"
  fi
  if [[ -e "$abyss_stack_mcp_operation_lock" || \
        -L "$abyss_stack_mcp_operation_lock" ]]; then
    [[ -f "$abyss_stack_mcp_operation_lock" && \
       ! -L "$abyss_stack_mcp_operation_lock" ]] || \
      aoa_die "abyss-stack MCP operation lock must be a regular non-symlink file"
  else
    (
      umask 077
      set -o noclobber
      : > "$abyss_stack_mcp_operation_lock"
    ) 2>/dev/null || true
    [[ -f "$abyss_stack_mcp_operation_lock" && \
       ! -L "$abyss_stack_mcp_operation_lock" ]] || \
      aoa_die "failed to create the abyss-stack MCP operation lock"
  fi
  chmod 0600 "$abyss_stack_mcp_operation_lock"
}

aoa_verify_abyss_stack_mcp_runtime() {
  local contour="${1:-all}"
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

  aoa_verify_abyss_stack_mcp_audit_journals "$contour"
  [[ -f "$abyss_stack_mcp_source_lock" && \
     ! -L "$abyss_stack_mcp_source_lock" ]] || \
    aoa_die "abyss-stack MCP source projection lock is unavailable"
  [[ -f "$abyss_stack_mcp_runtime_lock" && \
     ! -L "$abyss_stack_mcp_runtime_lock" ]] || \
    aoa_die "abyss-stack MCP runtime lock is unavailable"
  exec {source_lock_fd}< "$abyss_stack_mcp_source_lock"
  if ! /usr/bin/flock --shared --nonblock "$source_lock_fd"; then
    aoa_die "Configs sync or runtime provisioning holds the abyss-stack MCP source projection lock"
  fi
  exec {runtime_lock_fd}< "$abyss_stack_mcp_runtime_lock"
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
  [[ -f "${abyss_stack_mcp_venv}/bin/python" && \
     ! -L "${abyss_stack_mcp_venv}/bin/python" && \
     -x "${abyss_stack_mcp_venv}/bin/python" ]] || \
    aoa_die "abyss-stack MCP runtime Python must be an executable regular non-symlink file"
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
  recorded_content_digest="$(
    <"${abyss_stack_mcp_venv}/${content_marker}"
  )"
  [[ "$recorded_content_digest" =~ ^[0-9a-f]{64}$ ]] || \
    aoa_die "abyss-stack MCP runtime content marker is invalid"
  observed_content_digest="$(
    aoa_digest_abyss_stack_mcp_runtime "$abyss_stack_mcp_venv"
  )" || aoa_die "failed to digest the provisioned abyss-stack MCP runtime"
  if [[ "$recorded_identity" != "$expected_identity" || \
        "$observed_content_digest" != "$recorded_content_digest" ]]; then
    if [[ "$contour" != "read" ]] || \
       ! aoa_verify_abyss_stack_mcp_read_rollback_grant \
         "$recorded_identity" "$observed_content_digest"; then
      if [[ "$recorded_identity" != "$expected_identity" ]]; then
        aoa_die "abyss-stack MCP runtime source-and-lock identity mismatch"
      fi
      aoa_die "abyss-stack MCP runtime content digest mismatch"
    fi
  fi
  aoa_verify_abyss_stack_mcp_runtime_imports >/dev/null || \
    aoa_die "abyss-stack MCP runtime Python dependency/import check failed"
  exec {runtime_lock_fd}>&-
  exec {source_lock_fd}>&-
}

aoa_launch_verified_abyss_stack_mcp() {
  local contour="$1"
  local module="abyss_stack_mcp.server"

  [[ "${ABYSS_STACK_MCP_POLICY_FAMILY:-}" == "$contour" ]] || \
    aoa_die "verified abyss-stack MCP launch contour does not match the policy family"
  aoa_verify_abyss_stack_mcp_runtime "$contour"
  if [[ "$contour" == "internal_effect" ]]; then
    module="abyss_stack_mcp.effect_server"
  fi
  exec /usr/bin/env -u PYTHONHOME -u PYTHONPATH \
    "$abyss_stack_mcp_venv/bin/python" \
    -I -B -m "$module"
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
    [[ "$interpreter_suffix" =~ ^/bin/python([0-9]+([.][0-9]+)*)?$ ]] || \
      return 1
    # Direct console entry points bypass the systemd launcher, so bind Python's
    # no-bytecode mode into their published shebang. Otherwise a documented
    # canary invocation creates __pycache__ inside the content-addressed venv
    # and invalidates the other contour before its verifier can start.
    interpreter_suffix="${interpreter_suffix} -B"
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
  local provision_mode="${1:-manual}"
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
  local rollback_grant_temp=""
  local resolved_bootstrap_python=""
  local read_unit_was_active=0
  local bootstrap_unit_was_active=0
  local fallback_unit_was_active=0
  local read_fleet_quiesced=0
  local runtime_swapped=0
  local runtime_activated=0
  local organ_units_output=""
  local organ_unit=""
  local -a active_organ_read_units=()
  local -a repair_fallback_units=()
  local fallback_marker_temp=""
  local operation_lock_fd=""
  local runtime_lock_fd=""
  local source_lock_fd=""

  case "$provision_mode" in
    manual|repair)
      ;;
    *)
      aoa_die "unsupported abyss-stack MCP runtime provision mode: ${provision_mode}"
      ;;
  esac

  aoa_cleanup_abyss_stack_mcp_runtime_stage() {
    local exit_status="${1:-1}"

    trap - EXIT HUP INT TERM
    if [[ -n "$temp_venv" && \
          "$temp_venv" == "${abyss_stack_mcp_runtime_root}/.venv."* && \
          -d "$temp_venv" && ! -L "$temp_venv" ]]; then
      rm -rf -- "$temp_venv"
    fi
    if ((runtime_swapped && ! runtime_activated)) && \
       [[ -n "$backup_venv" && \
          "$backup_venv" == "${abyss_stack_mcp_runtime_root}/.venv.previous."* && \
          -d "$backup_venv" && ! -L "$backup_venv" ]]; then
      if ((${#repair_fallback_units[@]})); then
        systemctl --user stop "${repair_fallback_units[@]}" \
          >/dev/null 2>&1 || true
      fi
      if [[ -z "$runtime_lock_fd" ]]; then
        exec {runtime_lock_fd}<> "$abyss_stack_mcp_runtime_lock"
      fi
      if /usr/bin/flock --exclusive --nonblock "$runtime_lock_fd" && \
         [[ -d "$abyss_stack_mcp_venv" && \
            ! -L "$abyss_stack_mcp_venv" ]] && \
         rm -rf -- "$abyss_stack_mcp_venv" && \
         mv -- "$backup_venv" "$abyss_stack_mcp_venv"; then
        backup_venv=""
        runtime_swapped=0
        if [[ -f "$abyss_stack_mcp_repair_fallback" && \
              ! -L "$abyss_stack_mcp_repair_fallback" ]]; then
          rm -f -- "$abyss_stack_mcp_repair_fallback"
        fi
      else
        printf '%s\n' \
          'failed to restore the previous abyss-stack MCP runtime after fallback activation failure' \
          >&2
      fi
    fi
    if [[ -n "$backup_venv" && \
          "$backup_venv" == "${abyss_stack_mcp_runtime_root}/.venv.previous."* && \
          -d "$backup_venv" && ! -L "$backup_venv" ]]; then
      if ((runtime_swapped)); then
        printf '%s\n' \
          'preserving the previous MCP runtime backup because rollback did not complete' \
          >&2
      elif [[ ! -e "$abyss_stack_mcp_venv" && ! -L "$abyss_stack_mcp_venv" ]]; then
        mv -- "$backup_venv" "$abyss_stack_mcp_venv" || \
          printf '%s\n' \
            'failed to restore the previous abyss-stack MCP runtime during cleanup' \
            >&2
      else
        rm -rf -- "$backup_venv"
      fi
    fi
    if [[ -n "$rollback_grant_temp" && \
          "$rollback_grant_temp" == \
            "${abyss_stack_mcp_runtime_root}/.read-repair-rollback-grant."* ]]; then
      rm -f -- "$rollback_grant_temp"
    fi
    if [[ -n "$fallback_marker_temp" && \
          "$fallback_marker_temp" == \
            "${abyss_stack_mcp_admission_root}/.runtime-repair-fallback."* ]]; then
      rm -f -- "$fallback_marker_temp"
    fi
    if [[ -n "$runtime_lock_fd" ]]; then
      exec {runtime_lock_fd}>&-
      runtime_lock_fd=""
    fi
    if [[ -n "$source_lock_fd" ]]; then
      exec {source_lock_fd}>&-
      source_lock_fd=""
    fi
    if [[ -n "$operation_lock_fd" ]]; then
      exec {operation_lock_fd}>&-
      operation_lock_fd=""
    fi
    if ((read_fleet_quiesced)); then
      if ((runtime_activated)); then
        if ((${#repair_fallback_units[@]})) && \
           ! systemctl --user start "${repair_fallback_units[@]}"; then
          printf '%s\n' \
            'failed to restore the MCP repair fallback after runtime activation' \
            >&2
        fi
      elif ((runtime_swapped)); then
        printf '%s\n' \
          'not restarting the previous MCP read fleet because runtime rollback did not complete' \
          >&2
      else
        if ((read_unit_was_active)) && \
           ! systemctl --user start abyss-stack-mcp-read.service; then
          printf '%s\n' \
            'failed to restore abyss-stack MCP production read service during repair cleanup' \
            >&2
        fi
        if ((bootstrap_unit_was_active)) && \
           ! systemctl --user start abyss-stack-mcp-read-bootstrap.service; then
          printf '%s\n' \
            'failed to restore abyss-stack MCP bootstrap read service during repair cleanup' \
            >&2
        fi
        if ((fallback_unit_was_active)) && \
           ! systemctl --user start abyss-stack-mcp-read-fallback.service; then
          printf '%s\n' \
            'failed to restore abyss-stack MCP fallback read service during repair cleanup' \
            >&2
        fi
        for organ_unit in "${active_organ_read_units[@]}"; do
          if ! systemctl --user start "$organ_unit"; then
            printf 'failed to restore active MCP reader %s during repair cleanup\n' \
              "$organ_unit" >&2
          fi
        done
      fi
    fi
    exit "$exit_status"
  }

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
  if [[ "$provision_mode" == "repair" ]]; then
    if ! /usr/bin/flock --shared --nonblock "$source_lock_fd"; then
      aoa_die "Configs sync or another provisioner holds the abyss-stack MCP source projection lock"
    fi
  elif ! /usr/bin/flock --exclusive --nonblock "$source_lock_fd"; then
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
  if [[ -e "$abyss_stack_mcp_operation_lock" || \
        -L "$abyss_stack_mcp_operation_lock" ]]; then
    [[ -f "$abyss_stack_mcp_operation_lock" && \
       ! -L "$abyss_stack_mcp_operation_lock" ]] || \
      aoa_die "abyss-stack MCP operation lock must be a regular non-symlink file"
  else
    (
      umask 077
      set -o noclobber
      : > "$abyss_stack_mcp_operation_lock"
    ) 2>/dev/null || true
    [[ -f "$abyss_stack_mcp_operation_lock" && \
       ! -L "$abyss_stack_mcp_operation_lock" ]] || \
      aoa_die "failed to create the abyss-stack MCP operation lock"
  fi
  chmod 0600 "$abyss_stack_mcp_operation_lock"
  exec {operation_lock_fd}<> "$abyss_stack_mcp_operation_lock"
  if ! /usr/bin/flock --exclusive --nonblock "$operation_lock_fd"; then
    aoa_die "another provisioner or a managed non-read abyss-stack MCP plane holds the operation lock"
  fi
  if [[ -e "$abyss_stack_mcp_read_rollback_grant" || \
        -L "$abyss_stack_mcp_read_rollback_grant" ]]; then
    [[ -f "$abyss_stack_mcp_read_rollback_grant" && \
       ! -L "$abyss_stack_mcp_read_rollback_grant" ]] || \
      aoa_die "abyss-stack MCP read rollback grant must be a regular non-symlink file"
    [[ "$(stat -c '%a' "$abyss_stack_mcp_read_rollback_grant")" == "600" ]] || \
      aoa_die "abyss-stack MCP read rollback grant must use mode 0600"
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
  aoa_provision_abyss_stack_mcp_audit_journals
  aoa_provision_abyss_stack_mcp_observation_root
  aoa_provision_abyss_stack_mcp_admission_roots
  aoa_provision_abyss_stack_mcp_orchestration_root
  aoa_provision_abyss_stack_mcp_tasks_root
  aoa_provision_abyss_stack_mcp_effect_root

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
          -f "${abyss_stack_mcp_venv}/bin/python" && \
          ! -L "${abyss_stack_mcp_venv}/bin/python" && \
          -x "${abyss_stack_mcp_venv}/bin/python" ]] && \
       PYTHONDONTWRITEBYTECODE=1 \
         aoa_run_isolated_python \
           "${abyss_stack_mcp_venv}/bin/python" -m pip check >/dev/null && \
       aoa_verify_abyss_stack_mcp_runtime_imports >/dev/null; then
      deployed_digest="$(
        aoa_digest_abyss_stack_mcp_package "$abyss_stack_mcp_service_root"
      )" || \
        aoa_die "failed to recheck the deployed abyss-stack MCP package"
      [[ "$deployed_digest" == "$source_digest" ]] || \
        aoa_die "deployed abyss-stack MCP package changed during runtime verification"
      aoa_note "abyss-stack MCP runtime already provisioned for deployed source ${source_digest} and lock ${lock_digest}"
      exec {operation_lock_fd}>&-
      exec {source_lock_fd}>&-
      return 0
    fi
  fi

  exec {runtime_lock_fd}<> "$abyss_stack_mcp_runtime_lock"
  if [[ "$provision_mode" == "repair" ]]; then
    if ! /usr/bin/flock --shared --nonblock "$runtime_lock_fd"; then
      aoa_die "another provisioner holds the abyss-stack MCP runtime lock"
    fi
  elif ! /usr/bin/flock --exclusive --nonblock "$runtime_lock_fd"; then
    aoa_die "another provisioner or a managed abyss-stack MCP plane holds the runtime lock"
  fi
  if [[ "$provision_mode" == "repair" ]]; then
    if ! aoa_require_abyss_stack_mcp_units_stopped 1; then
      aoa_die "$abyss_stack_mcp_units_error"
    fi
  elif ! aoa_require_abyss_stack_mcp_units_stopped; then
    aoa_die "$abyss_stack_mcp_units_error"
  fi

  temp_venv="$(mktemp -d "${abyss_stack_mcp_runtime_root}/.venv.XXXXXX")"
  trap 'aoa_cleanup_abyss_stack_mcp_runtime_stage "$?"' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
  if ! aoa_run_isolated_python \
    "$abyss_stack_mcp_bootstrap_python" -m venv --copies "$temp_venv"; then
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
         'import abyss_stack_mcp, aoa_sdk, mcp, pydantic; from importlib.metadata import version; assert version("aoa-sdk") == "0.10.2"' >/dev/null; then
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

  if [[ "$provision_mode" == "repair" ]]; then
    if systemctl --user is-active --quiet abyss-stack-mcp-read.service; then
      read_unit_was_active=1
    fi
    if systemctl --user is-active --quiet \
        abyss-stack-mcp-read-bootstrap.service; then
      bootstrap_unit_was_active=1
    fi
    if systemctl --user is-active --quiet \
        abyss-stack-mcp-read-fallback.service; then
      fallback_unit_was_active=1
    fi
    organ_units_output="$(
      systemctl --user list-units \
        --type=service \
        --state=active,activating,reloading \
        --no-legend \
        --plain \
        'aoa-organ-mcp-read@*.service' \
        'aoa-organ-mcp-read-bootstrap@*.service' \
        'aoa-organ-mcp-read-fallback@*.service'
    )" || aoa_die "failed to enumerate active MCP organ readers before runtime activation"
    while read -r organ_unit _; do
      [[ -n "$organ_unit" ]] || continue
      [[ "$organ_unit" =~ ^aoa-organ-mcp-read(-(bootstrap|fallback))?@[A-Za-z0-9_.-]+\.service$ ]] || \
        aoa_die "unsafe active MCP organ reader unit name: ${organ_unit}"
      active_organ_read_units+=("$organ_unit")
      if [[ "$organ_unit" == aoa-organ-mcp-read-fallback@* ]]; then
        repair_fallback_units+=("$organ_unit")
      else
        organ_unit="${organ_unit/aoa-organ-mcp-read-bootstrap@/aoa-organ-mcp-read@}"
        repair_fallback_units+=(
          "${organ_unit/aoa-organ-mcp-read@/aoa-organ-mcp-read-fallback@}"
        )
      fi
    done <<< "$organ_units_output"
    if ((read_unit_was_active || bootstrap_unit_was_active || fallback_unit_was_active)); then
      repair_fallback_units=(
        abyss-stack-mcp-read-fallback.service
        "${repair_fallback_units[@]}"
      )
    fi
    if ((${#repair_fallback_units[@]})) && \
       [[ -e "$abyss_stack_mcp_repair_fallback" || \
          -L "$abyss_stack_mcp_repair_fallback" ]]; then
      aoa_die "an unresolved MCP runtime-repair fallback already exists"
    fi
    if ((read_unit_was_active || bootstrap_unit_was_active || fallback_unit_was_active)); then
      observed_content_digest="$(
        aoa_digest_abyss_stack_mcp_runtime "$abyss_stack_mcp_venv"
      )" || aoa_die "failed to capture the live abyss-stack MCP rollback runtime"
      [[ "$existing_identity" =~ ^[0-9a-f]{64}:[0-9a-f]{64}$ ]] || \
        aoa_die "live abyss-stack MCP rollback runtime identity is invalid"
      [[ "$existing_content_digest" =~ ^[0-9a-f]{64}$ && \
         "$observed_content_digest" == "$existing_content_digest" ]] || \
        aoa_die "live abyss-stack MCP rollback runtime content is not exact"
      PYTHONDONTWRITEBYTECODE=1 \
        aoa_run_isolated_python \
          "${abyss_stack_mcp_venv}/bin/python" -m pip check >/dev/null || \
        aoa_die "live abyss-stack MCP rollback runtime failed dependency verification"
      aoa_verify_abyss_stack_mcp_runtime_imports >/dev/null || \
        aoa_die "live abyss-stack MCP rollback runtime failed import verification"
      rollback_grant_temp="$(
        mktemp \
          "${abyss_stack_mcp_runtime_root}/.read-repair-rollback-grant.XXXXXX"
      )"
      chmod 0600 "$rollback_grant_temp"
      printf '%s:%s\n' "$observed_content_digest" "$existing_identity" > \
        "$rollback_grant_temp"
      mv -f -- "$rollback_grant_temp" "$abyss_stack_mcp_read_rollback_grant"
      rollback_grant_temp=""
    fi
    read_fleet_quiesced=1
    if ! systemctl --user stop \
        abyss-stack-mcp-read.service \
        abyss-stack-mcp-read-bootstrap.service \
        abyss-stack-mcp-read-fallback.service \
        "${active_organ_read_units[@]}"; then
      aoa_die "failed to quiesce the abyss-stack MCP read plane for runtime activation"
    fi
    if ! aoa_require_abyss_stack_mcp_units_stopped; then
      aoa_die "$abyss_stack_mcp_units_error"
    fi
    if ! /usr/bin/flock --exclusive --nonblock "$runtime_lock_fd"; then
      aoa_die "failed to obtain the exclusive abyss-stack MCP runtime lock after read-plane quiescence"
    fi
  elif ! aoa_require_abyss_stack_mcp_units_stopped; then
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
  temp_venv=""
  runtime_swapped=1
  if ((${#repair_fallback_units[@]})); then
    if ! fallback_marker_temp="$(
      mktemp \
        "${abyss_stack_mcp_admission_root}/.runtime-repair-fallback.XXXXXX"
    )"; then
      aoa_die "failed to stage the MCP repair fallback marker"
    fi
    if ! chmod 0600 "$fallback_marker_temp" || \
       ! printf '%s\n' "${repair_fallback_units[@]}" > "$fallback_marker_temp" || \
       ! mv -- "$fallback_marker_temp" "$abyss_stack_mcp_repair_fallback"; then
      aoa_die "failed to publish the MCP repair fallback marker"
    fi
    fallback_marker_temp=""
  fi
  exec {runtime_lock_fd}>&-
  runtime_lock_fd=""
  if ((${#repair_fallback_units[@]})); then
    systemctl --user reset-failed "${repair_fallback_units[@]}" \
      >/dev/null 2>&1 || true
    systemctl --user start "${repair_fallback_units[@]}" || \
      aoa_die "failed to start the MCP repair fallback after runtime activation"
    for organ_unit in "${repair_fallback_units[@]}"; do
      systemctl --user is-active --quiet "$organ_unit" || \
        aoa_die "MCP repair fallback did not become active: ${organ_unit}"
    done
  fi
  runtime_activated=1
  rm -f -- "$abyss_stack_mcp_read_rollback_grant"
  if [[ -n "$backup_venv" && -d "$backup_venv" ]]; then
    rm -rf -- "$backup_venv"
  fi
  backup_venv=""
  read_fleet_quiesced=0
  trap - EXIT HUP INT TERM
  exec {source_lock_fd}>&-
  exec {operation_lock_fd}>&-
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
if ((provision_organ_mcp_candidate_auth || install_mcp_http_codex_client)); then
  aoa_provision_organ_mcp_candidate_auth
elif ((provision_organ_mcp_read_auth)); then
  aoa_provision_organ_mcp_read_auth
fi
if ((provision_abyss_stack_mcp_auth)); then
  aoa_provision_abyss_stack_mcp_auth
fi
if ((rotate_abyss_stack_mcp_auth)); then
  aoa_rotate_abyss_stack_mcp_auth
fi
if ((provision_ovms_auth)); then
  aoa_provision_ovms_auth
fi
if ((provision_abyss_stack_mcp_runtime)); then
  aoa_provision_abyss_stack_mcp_runtime manual
fi
if ((repair_abyss_stack_mcp_runtime)); then
  aoa_provision_abyss_stack_mcp_runtime repair
fi
if ((verify_abyss_stack_mcp_runtime)); then
  aoa_verify_abyss_stack_mcp_runtime \
    "$verify_abyss_stack_mcp_runtime_contour"
fi
if ((verify_abyss_stack_mcp_repair_eligibility)); then
  aoa_verify_abyss_stack_mcp_repair_eligibility
fi
if ((launch_verified_abyss_stack_mcp)); then
  aoa_launch_verified_abyss_stack_mcp \
    "$launch_verified_abyss_stack_mcp_contour"
fi
if ((enable_abyss_stack_mcp_auto_repair)); then
  aoa_set_abyss_stack_mcp_auto_repair_policy enabled
fi
if ((disable_abyss_stack_mcp_auto_repair)); then
  aoa_set_abyss_stack_mcp_auto_repair_policy disabled
fi
if ((install_mcp_http_codex_client)); then
  aoa_install_mcp_http_codex_client
fi
if ((remove_mcp_http_codex_client)); then
  aoa_remove_mcp_http_codex_client
fi
 if ((provision_mcp_http_auth || provision_organ_mcp_read_auth || provision_organ_mcp_candidate_auth || provision_abyss_stack_mcp_auth || rotate_abyss_stack_mcp_auth || provision_ovms_auth || provision_abyss_stack_mcp_runtime || repair_abyss_stack_mcp_runtime || verify_abyss_stack_mcp_runtime || verify_abyss_stack_mcp_repair_eligibility || launch_verified_abyss_stack_mcp || enable_abyss_stack_mcp_auto_repair || disable_abyss_stack_mcp_auto_repair || install_mcp_http_codex_client || remove_mcp_http_codex_client)) && \
  ((!enable_now && !restart_now && !link_all_user_units && !link_system_units && !selection_set && !overlay_set)); then
  exit 0
fi

unit_source="${AOA_CONFIGS_ROOT}/systemd/user/podman-compose-abyss.service"
unit_manifest="${AOA_CONFIGS_ROOT}/systemd/user/managed-units.txt"
system_unit_manifest="${AOA_CONFIGS_ROOT}/systemd/system/managed-units.txt"
unit_target_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
quadlet_target_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/containers/systemd"
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
  local target_path
  local backup_path
  local previous_target

  if [[ "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.container$ ]]; then
    mkdir -p "$quadlet_target_dir"
    target_path="${quadlet_target_dir}/${unit_name}"
  elif [[ "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.(service|timer|path|socket)$ ]]; then
    target_path="${unit_target_dir}/${unit_name}"
  else
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
  aoa_provision_abyss_stack_mcp_unit_operation_lock
  while IFS= read -r unit_name || [[ -n "$unit_name" ]]; do
    unit_name="${unit_name%%#*}"
    unit_name="${unit_name#"${unit_name%%[![:space:]]*}"}"
    unit_name="${unit_name%"${unit_name##*[![:space:]]}"}"
    [[ -n "$unit_name" ]] || continue
    aoa_link_user_unit "$unit_name"
  done < "$unit_manifest"
else
  aoa_link_user_unit "podman-compose-abyss.service"
  aoa_link_user_unit "abyss-ovms.container"
  aoa_link_user_unit "abyss-ovms.socket"
  aoa_link_user_unit "abyss-ovms-unix.socket"
  aoa_link_user_unit "abyss-ovms-proxy.service"
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
