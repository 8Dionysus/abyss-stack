#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AOA_SOURCE_ROOT:-$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)}"
# shellcheck source=scripts/aoa-lib.sh
source "${REPO_ROOT}/scripts/aoa-lib.sh"

strict_mode=0
selector_args=()
while (($#)); do
  case "$1" in
    --strict)
      strict_mode=1
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

errors=0
warnings=0

doctor_ok() {
  aoa_note "ok   $1"
}

doctor_warn() {
  aoa_note "warn $1"
  warnings=$((warnings + 1))
}

doctor_fail() {
  aoa_note "fail $1"
  errors=$((errors + 1))
}

doctor_flag_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
  esac
  return 1
}

doctor_env_file_value() {
  local key="$1"
  local env_file="$2"
  local raw_line line trimmed value

  [[ -f "$env_file" ]] || return 1

  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    line="${raw_line%%#*}"
    trimmed="$(aoa_trim "$line")"
    [[ -n "$trimmed" ]] || continue
    [[ "$trimmed" == "${key}="* ]] || continue

    value="${trimmed#*=}"
    value="$(aoa_trim "$value")"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    printf '%s' "$value"
    return 0
  done < "$env_file"

  return 1
}

doctor_report_json_levels() {
  local level message

  while IFS=$'\t' read -r level message || [[ -n "${level:-}" ]]; do
    [[ -n "${level:-}" ]] || continue
    case "$level" in
      OK)
        doctor_ok "$message"
        ;;
      WARN)
        doctor_warn "$message"
        ;;
      FAIL)
        doctor_fail "$message"
        ;;
      *)
        doctor_warn "$level ${message:-}"
        ;;
    esac
  done
}

doctor_check_machine_fit_record() {
  local record_path="$1"
  local max_age_hours="${AOA_MACHINE_FIT_MAX_AGE_HOURS:-720}"
  local report

  report="$(
    python3 - "$record_path" "$max_age_hours" <<'PY'
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
max_age_hours = float(sys.argv[2])


def emit(level: str, message: str) -> None:
    print(f"{level}\t{message}")


def parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def os_release_value(key: str) -> str | None:
    release_path = Path("/etc/os-release")
    if not release_path.exists():
        return None
    for raw_line in release_path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line:
            continue
        raw_key, raw_value = raw_line.split("=", 1)
        if raw_key == key:
            return raw_value.strip().strip('"')
    return None


try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    emit("WARN", f"machine-fit record unreadable: {path} ({exc})")
    raise SystemExit(0)

warnings = 0
if payload.get("artifact_kind") != "aoa.machine-fit":
    emit("WARN", f"machine-fit record has unexpected artifact_kind at {path}")
    warnings += 1

captured_at = parse_dt(payload.get("captured_at"))
if captured_at is None:
    emit("WARN", f"machine-fit record has no parseable captured_at: {path}")
    warnings += 1
else:
    age_hours = (datetime.now(timezone.utc) - captured_at).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        emit(
            "WARN",
            f"machine-fit record stale ({age_hours:.1f}h > {max_age_hours:.1f}h): {path}",
        )
        warnings += 1

machine = payload.get("machine") if isinstance(payload.get("machine"), dict) else {}
record_kernel = machine.get("kernel_release")
current_kernel = platform.release()
if not isinstance(record_kernel, str) or not record_kernel:
    emit("WARN", "machine-fit record is missing machine.kernel_release; refresh machine-fit")
    warnings += 1
elif record_kernel != current_kernel:
    emit(
        "WARN",
        f"machine-fit kernel mismatch: record={record_kernel} current={current_kernel}; refresh machine-fit",
    )
    warnings += 1

record_os = machine.get("os_version_id")
current_os = os_release_value("VERSION_ID")
if not isinstance(record_os, str) or not record_os:
    emit("WARN", "machine-fit record is missing machine.os_version_id; refresh machine-fit")
    warnings += 1
elif current_os and record_os != current_os:
    emit(
        "WARN",
        f"machine-fit OS version mismatch: record={record_os} current={current_os}; refresh machine-fit",
    )
    warnings += 1

verdict = payload.get("fit_verdict") if isinstance(payload.get("fit_verdict"), dict) else {}
status = verdict.get("status")
if status not in {"qualified", "qualified-noisy-host"}:
    emit("WARN", f"machine-fit verdict is {status or 'missing'}; review before launch")
    warnings += 1

if warnings == 0:
    emit("OK", f"machine-fit record current enough {path}")
PY
  )"
  doctor_report_json_levels <<< "$report"
}

doctor_check_machine_bridge_record() {
  local record_path="$1"
  local max_age_hours="${AOA_MACHINE_BRIDGE_MAX_AGE_HOURS:-24}"
  local report

  report="$(
    python3 - "$record_path" "$max_age_hours" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

path = Path(sys.argv[1])
max_age_hours = float(sys.argv[2])


def emit(level: str, message: str) -> None:
    print(f"{level}\t{message}")


def parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_json(*command: str) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    emit("WARN", f"machine-bridge record unreadable: {path} ({exc})")
    raise SystemExit(0)

warnings = 0
if payload.get("artifact_kind") != "aoa.machine-bridge":
    emit("WARN", f"machine-bridge record has unexpected artifact_kind at {path}")
    warnings += 1

if payload.get("status") != "ready":
    emit("WARN", f"machine-bridge record status is {payload.get('status') or 'missing'}; refresh machine bridge")
    warnings += 1

summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
if summary.get("stack_bridge_export_ok") is not True:
    emit("WARN", "machine-bridge record does not prove stack_bridge_export_ok")
    warnings += 1
if summary.get("stack_bridge_validate_ok") is not True:
    emit("WARN", "machine-bridge record does not prove stack_bridge_validate_ok")
    warnings += 1

captured_at = parse_dt(payload.get("captured_at"))
if captured_at is None:
    emit("WARN", f"machine-bridge record has no parseable captured_at: {path}")
    warnings += 1
else:
    age_hours = (datetime.now(timezone.utc) - captured_at).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        emit(
            "WARN",
            f"machine-bridge record stale ({age_hours:.1f}h > {max_age_hours:.1f}h): {path}",
        )
        warnings += 1

current_bridge = run_json("abyss-machine", "bridge", "--json")
current_stack_bridge = run_json("abyss-machine", "stack-bridge", "export", "--json")
if current_bridge is None:
    emit("WARN", "live abyss-machine bridge probe unavailable; refresh or repair abyss-machine bridge")
    warnings += 1
if current_stack_bridge is None:
    emit("WARN", "live abyss-machine stack-bridge export probe unavailable; refresh or repair abyss-machine stack bridge")
    warnings += 1
host_bridge = payload.get("host_bridge") if isinstance(payload.get("host_bridge"), dict) else {}
record_bridge_version = host_bridge.get("bridge_version")
current_bridge_version = current_bridge.get("version") if isinstance(current_bridge, dict) else None
if (
    isinstance(record_bridge_version, str)
    and isinstance(current_bridge_version, str)
    and record_bridge_version != current_bridge_version
):
    emit(
        "WARN",
        f"machine-bridge host bridge version mismatch: record={record_bridge_version} current={current_bridge_version}; refresh machine bridge",
    )
    warnings += 1

record_stack_summary = host_bridge.get("stack_bridge_summary") if isinstance(host_bridge.get("stack_bridge_summary"), dict) else {}
current_stack_summary = current_stack_bridge.get("summary") if isinstance(current_stack_bridge, dict) and isinstance(current_stack_bridge.get("summary"), dict) else {}
for key in ("layers", "refs", "stack_bridge_commands"):
    record_value = record_stack_summary.get(key)
    current_value = current_stack_summary.get(key)
    if record_value is not None and current_value is not None and record_value != current_value:
        emit(
            "WARN",
            f"machine-bridge stack summary mismatch for {key}: record={record_value} current={current_value}; refresh machine bridge",
        )
        warnings += 1

record_named = sorted(record_stack_summary.get("named_bridges") or [])
current_named = sorted(current_stack_summary.get("named_bridges") or [])
if record_named and current_named and record_named != current_named:
    emit("WARN", "machine-bridge named bridge set changed; refresh machine bridge")
    warnings += 1

if warnings == 0:
    emit("OK", f"machine-bridge record current enough {path}")
PY
  )"
  doctor_report_json_levels <<< "$report"
}

doctor_federated_consumer_reason() {
  local env_file="${AOA_STACK_ROOT}/Secrets/Configs/langchain-api.env"
  local value

  if has_module "44-llamacpp-agent-sidecar.yml"; then
    printf '%s' "selected runtime includes 44-llamacpp-agent-sidecar.yml, which hard-enables AOA_FEDERATED_RUN_ENABLED=true"
    return 0
  fi

  if ! has_module "41-agent-api.yml"; then
    return 1
  fi

  if [[ -n "${AOA_FEDERATED_RUN_ENABLED+x}" ]]; then
    if doctor_flag_truthy "${AOA_FEDERATED_RUN_ENABLED}"; then
      printf '%s' "the current shell environment enables AOA_FEDERATED_RUN_ENABLED=true"
      return 0
    fi
    return 1
  fi

  if value="$(doctor_env_file_value "AOA_FEDERATED_RUN_ENABLED" "$env_file")"; then
    if doctor_flag_truthy "$value"; then
      printf '%s' "the langchain-api runtime secret enables AOA_FEDERATED_RUN_ENABLED=true"
      return 0
    fi
  fi

  return 1
}

check_required_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    doctor_ok "cmd  $name"
  else
    doctor_fail "cmd  $name not found"
  fi
}

has_module() {
  local target="$1"
  local module
  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

uname_s="$(uname -s)"
aoa_note "stack root: ${AOA_STACK_ROOT}"
aoa_note "configs root: ${AOA_CONFIGS_ROOT}"
aoa_note "vault root: ${AOA_VAULT_ROOT}"

if [[ "$uname_s" == "Linux" ]]; then
  doctor_ok "platform Linux"
else
  doctor_warn "platform ${uname_s}; Fedora-first runtime expects Linux"
fi

if [[ "${AOA_STACK_ROOT}" == "/srv/AbyssOS/abyss-stack" ]]; then
  doctor_ok "canonical stack root ${AOA_STACK_ROOT}"
else
  doctor_warn "non-canonical stack root ${AOA_STACK_ROOT}"
fi

check_required_cmd podman
check_required_cmd rsync
check_required_cmd curl

if podman compose version >/dev/null 2>&1; then
  doctor_ok "compose backend podman compose"
elif command -v podman-compose >/dev/null 2>&1; then
  doctor_ok "compose backend podman-compose"
else
  doctor_fail "compose backend unavailable"
fi

if podman info >/dev/null 2>&1; then
  doctor_ok "podman info"
else
  doctor_warn "podman installed but not currently usable"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl --user show-environment >/dev/null 2>&1; then
    doctor_ok "systemctl --user"
  else
    doctor_warn "systemctl exists but user instance unavailable"
  fi
else
  doctor_warn "systemctl not found"
fi

if has_module "31-intel-inference.yml"; then
  if [[ -e /dev/dri ]]; then
    doctor_ok "/dev/dri present for intel-aware selection"
  else
    doctor_warn "/dev/dri missing; selected preset/profile includes Intel-aware inference"
  fi
else
  doctor_ok "intel device not required for current selection"
fi

if has_module "51-browser-tools.yml" || has_module "60-monitoring.yml"; then
  doctor_ok "internal-only services selected; use aoa-smoke --with-internal after startup"
fi

federated_consumer_reason=""
if ! has_module "43-federation-router.yml" && federated_consumer_reason="$(doctor_federated_consumer_reason)"; then
  doctor_warn "federated advisory consumer is enabled but the federation profile is not selected; ${federated_consumer_reason}. Add --profile federation or use agent-federation/intel-federation before startup, or disable AOA_FEDERATED_RUN_ENABLED"
fi

machine_fit_path="${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
if [[ -f "${machine_fit_path}" ]]; then
  doctor_check_machine_fit_record "${machine_fit_path}"
else
  doctor_warn "machine-fit record missing; run ${AOA_CONFIGS_ROOT}/scripts/aoa-machine-fit after bootstrap"
fi

machine_bridge_path="${AOA_STACK_ROOT}/Logs/machine-bridge/latest/latest.private.json"
if command -v abyss-machine >/dev/null 2>&1; then
  if bridge_payload="$(abyss-machine stack-bridge validate --json 2>/dev/null)" \
    && python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(0 if data.get("ok") else 1)' <<<"${bridge_payload}"; then
    doctor_ok "abyss-machine stack bridge validates"
  else
    doctor_warn "abyss-machine stack bridge did not validate; run abyss-machine stack-bridge validate --json"
  fi
  if [[ -f "${machine_bridge_path}" ]]; then
    doctor_check_machine_bridge_record "${machine_bridge_path}"
  else
    doctor_warn "machine-bridge record missing; run ${AOA_CONFIGS_ROOT}/scripts/aoa-machine-bridge --write-latest"
  fi
else
  doctor_warn "abyss-machine command not found; stack-side machine bridge is unavailable on this host"
fi

if [[ -r /proc/loadavg ]]; then
  load_1m="$(awk '{print $1}' /proc/loadavg 2>/dev/null || true)"
  cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
  if [[ -n "${load_1m}" && -n "${cpu_count}" ]]; then
    if python3 - "$load_1m" "$cpu_count" <<'PY'
import sys
load = float(sys.argv[1])
cpus = int(sys.argv[2])
sys.exit(0 if load > (cpus * 0.50) else 1)
PY
    then
      doctor_warn "host loadavg ${load_1m} is noisy for latency-sensitive trials on ${cpu_count} logical CPUs"
    else
      doctor_ok "host load envelope looks reasonable for latency-sensitive work"
    fi
  fi
fi

if command -v findmnt >/dev/null 2>&1; then
  if findmnt "${AOA_VAULT_ROOT}" >/dev/null 2>&1; then
    doctor_ok "vault mount ${AOA_VAULT_ROOT}"
  else
    doctor_warn "vault mount ${AOA_VAULT_ROOT} not present"
  fi
else
  doctor_warn "findmnt not found; cannot check vault mount"
fi

if ((errors > 0)); then
  aoa_die "doctor found ${errors} hard errors"
fi

if ((strict_mode)) && ((warnings > 0)); then
  aoa_die "doctor found ${warnings} warnings in strict mode"
fi

aoa_note "doctor check passed"
if ((warnings > 0)); then
  aoa_note "warnings: ${warnings}"
fi
