#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

force=0
dry_run=0
method="recreate"
wait_game_guard_clear=0
wait_resource_plan_clear=0
wait_timeout_sec=3600
wait_poll_sec=60

while (($#)); do
  case "$1" in
    --force)
      force=1
      ;;
    --dry-run)
      dry_run=1
      ;;
    --wait-game-guard-clear)
      wait_game_guard_clear=1
      ;;
    --wait-resource-plan-clear)
      wait_resource_plan_clear=1
      ;;
    --wait-timeout-sec)
      shift
      (($#)) || aoa_die "missing value after --wait-timeout-sec"
      wait_timeout_sec="$1"
      ;;
    --wait-timeout-sec=*)
      wait_timeout_sec="${1#*=}"
      ;;
    --wait-poll-sec)
      shift
      (($#)) || aoa_die "missing value after --wait-poll-sec"
      wait_poll_sec="$1"
      ;;
    --wait-poll-sec=*)
      wait_poll_sec="${1#*=}"
      ;;
    --method)
      shift
      (($#)) || aoa_die "missing value after --method"
      method="$1"
      ;;
    --method=*)
      method="${1#*=}"
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

[[ "$wait_timeout_sec" =~ ^[0-9]+$ ]] || aoa_die "--wait-timeout-sec must be a non-negative integer"
[[ "$wait_poll_sec" =~ ^[1-9][0-9]*$ ]] || aoa_die "--wait-poll-sec must be a positive integer"

case "$method" in
  reload|recreate|restart)
    ;;
  *)
    aoa_die "--method must be reload, recreate, or restart"
    ;;
esac

status_dir="${AOA_STACK_ROOT}/Logs/resource-guards/latest"
mkdir -p "$status_dir"
pre_status="${status_dir}/pre-apply.json"
post_status="${status_dir}/post-apply.json"
pre_service_selection_status="${status_dir}/pre-service-selection.json"
post_service_selection_status="${status_dir}/post-service-selection.json"
game_guard_status="${status_dir}/game-guard.json"
pre_resource_plan_status="${status_dir}/pre-resource-plan.json"
post_resource_plan_status="${status_dir}/post-resource-plan.json"
resource_plan_status="$pre_resource_plan_status"
pre_podman_stats="${status_dir}/pre-podman-stats.txt"
post_podman_stats="${status_dir}/post-podman-stats.txt"
pre_memory_status="${status_dir}/pre-memory.txt"
post_memory_status="${status_dir}/post-memory.txt"
pre_protected_units="${status_dir}/pre-protected-units.txt"
post_protected_units="${status_dir}/post-protected-units.txt"
protected_units=(
  abyss-tts-server.service
  abyss-dictation-server.service
  abyss-tts-keepwarm.timer
  podman-compose-abyss.service
)

status_json() {
  "${SCRIPTS_DIR}/aoa-status" --resource-guards --json
}

service_selection_json() {
  "${SCRIPTS_DIR}/aoa-status" --service-selection --json
}

capture_runtime_snapshot() {
  local podman_stats_path="$1"
  local memory_status_path="$2"

  {
    date -Is
    uptime || true
    free -h || true
    printf '\n/proc/pressure/memory:\n'
    cat /proc/pressure/memory || true
  } > "$memory_status_path"

  if command -v podman >/dev/null 2>&1; then
    podman stats --no-stream > "$podman_stats_path" 2>&1 || true
  else
    printf 'podman unavailable\n' > "$podman_stats_path"
  fi
}

capture_protected_units() {
  local output_path="$1"

  {
    date -Is
    systemctl --user is-active "${protected_units[@]}" || true
  } > "$output_path" 2>&1
}

protected_units_ok() {
  local output_path="$1"
  local active_count

  active_count="$(grep -c '^active$' "$output_path" || true)"
  [[ "$active_count" -eq "${#protected_units[@]}" ]]
}

apply_resource_guard_method() {
  case "$method" in
    reload|restart)
      systemctl --user "$method" podman-compose-abyss.service
      ;;
    recreate)
      systemctl --user set-environment AOA_UP_FORCE_RECREATE=1
      trap 'systemctl --user unset-environment AOA_UP_FORCE_RECREATE >/dev/null 2>&1 || true' RETURN
      systemctl --user reload podman-compose-abyss.service
      systemctl --user unset-environment AOA_UP_FORCE_RECREATE
      trap - RETURN
      ;;
  esac
}

describe_apply_action() {
  case "$method" in
    reload)
      printf 'systemctl --user reload podman-compose-abyss.service'
      ;;
    restart)
      printf 'systemctl --user restart podman-compose-abyss.service'
      ;;
    recreate)
      printf 'systemctl --user set-environment AOA_UP_FORCE_RECREATE=1; systemctl --user reload podman-compose-abyss.service; systemctl --user unset-environment AOA_UP_FORCE_RECREATE'
      ;;
  esac
}

read_game_guard_active() {
  if command -v abyss-machine >/dev/null 2>&1; then
    if abyss-machine processes game-guard --json > "$game_guard_status"; then
      json_field "$game_guard_status" "active" || printf 'unknown'
      return
    fi
    aoa_note "game guard check failed; see ${game_guard_status}" >&2
  else
    aoa_note "abyss-machine unavailable; game guard check skipped" >&2
  fi
  printf 'unknown'
}

wait_for_game_guard_clear() {
  local started now elapsed
  started="$(date +%s)"

  while [[ "$game_guard_active" == "true" ]]; do
    if ((wait_timeout_sec > 0)); then
      now="$(date +%s)"
      elapsed=$((now - started))
      if ((elapsed >= wait_timeout_sec)); then
        aoa_die "game guard still active after ${wait_timeout_sec}s; refusing to ${method} podman-compose-abyss.service without --force"
      fi
    fi

    aoa_note "game guard is active; waiting ${wait_poll_sec}s before ${method} apply"
    sleep "$wait_poll_sec"
    game_guard_active="$(read_game_guard_active)"
  done
}

read_resource_plan_ok() {
  if command -v abyss-machine >/dev/null 2>&1; then
    if abyss-machine resource plan --class medium --kind generic --unattended --json > "$resource_plan_status"; then
      json_field "$resource_plan_status" "ok" || printf 'unknown'
      return
    fi
    if [[ -s "$resource_plan_status" ]]; then
      json_field "$resource_plan_status" "ok" || printf 'unknown'
      return
    fi
    aoa_note "resource plan check failed; see ${resource_plan_status}" >&2
  else
    aoa_note "abyss-machine unavailable; resource plan check skipped" >&2
  fi
  printf 'unknown'
}

resource_plan_block_reasons() {
  python3 - "$resource_plan_status" <<'PY'
import json
import sys
from pathlib import Path

try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

reasons = payload.get("blocked_reasons")
if isinstance(reasons, list) and reasons:
    print(",".join(str(item) for item in reasons))
PY
}

wait_for_resource_plan_clear() {
  local started now elapsed reasons
  started="$(date +%s)"

  while [[ "$resource_plan_ok" == "false" ]]; do
    if ((wait_timeout_sec > 0)); then
      now="$(date +%s)"
      elapsed=$((now - started))
      if ((elapsed >= wait_timeout_sec)); then
        reasons="$(resource_plan_block_reasons)"
        aoa_die "resource plan still blocks after ${wait_timeout_sec}s (${reasons:-no details}); refusing to ${method} podman-compose-abyss.service without --force"
      fi
    fi

    reasons="$(resource_plan_block_reasons)"
    aoa_note "resource plan blocks apply (${reasons:-no details}); waiting ${wait_poll_sec}s"
    sleep "$wait_poll_sec"
    resource_plan_ok="$(read_resource_plan_ok)"
  done
}

json_field() {
  local path="$1"
  local expression="$2"
  python3 - "$path" "$expression" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expression = sys.argv[2].split(".")
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

for part in expression:
    if not part:
        continue
    if not isinstance(value, dict) or part not in value:
        raise SystemExit(1)
    value = value[part]

if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

status_json > "$pre_status"
service_selection_json > "$pre_service_selection_status"
capture_runtime_snapshot "$pre_podman_stats" "$pre_memory_status"
capture_protected_units "$pre_protected_units"
pre_guard_status="$(json_field "$pre_status" "summary.status" || true)"
pre_service_selection="$(json_field "$pre_service_selection_status" "summary.status" || true)"
staged_count="$(python3 - "$pre_status" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = payload.get("summary", {})
print(summary.get("staged_not_applied", summary.get("counts", {}).get("staged_not_applied", 0)))
PY
)"

aoa_note "resource guard status before apply: ${pre_guard_status:-unknown} staged=${staged_count}"
aoa_note "service selection before apply: ${pre_service_selection:-unknown}"

if [[ "$pre_guard_status" == "applied" ]]; then
  aoa_note "resource guards already applied; no runtime action needed"
  exit 0
fi

game_guard_active="$(read_game_guard_active)"

if [[ "$game_guard_active" == "true" && "$force" -ne 1 ]]; then
  if ((wait_game_guard_clear)); then
    if ((dry_run)); then
      aoa_note "dry run: would wait for game guard to clear before ${method} apply (timeout=${wait_timeout_sec}s poll=${wait_poll_sec}s)"
    else
      wait_for_game_guard_clear
    fi
  else
    aoa_die "game guard is active; refusing to ${method} podman-compose-abyss.service without --force"
  fi
fi

resource_plan_ok="$(read_resource_plan_ok)"
if [[ "$resource_plan_ok" == "false" && "$force" -ne 1 ]]; then
  if ((dry_run)); then
    if ((wait_resource_plan_clear)); then
      aoa_note "dry run: would wait for resource plan to allow medium generic unattended work before ${method} apply (timeout=${wait_timeout_sec}s poll=${wait_poll_sec}s)"
    else
      aoa_note "dry run: resource plan would block non-forced ${method} apply ($(resource_plan_block_reasons)); add --wait-resource-plan-clear to wait"
    fi
  elif ((wait_resource_plan_clear)); then
    wait_for_resource_plan_clear
  else
    aoa_die "resource plan blocks ${method} apply ($(resource_plan_block_reasons)); rerun with --wait-resource-plan-clear or --force"
  fi
fi

if [[ "$resource_plan_ok" == "unknown" && "$force" -ne 1 ]]; then
  if ((dry_run)); then
    aoa_note "dry run: resource plan status is unknown; non-forced apply would continue with game guard evidence only"
  else
    aoa_note "resource plan status is unknown; continuing with game guard evidence only"
  fi
fi

if ((dry_run)); then
  aoa_note "dry run: would $(describe_apply_action)"
  aoa_note "pre-apply status: ${pre_status}"
  aoa_note "pre-apply service selection: ${pre_service_selection_status}"
  aoa_note "pre-apply podman stats: ${pre_podman_stats}"
  aoa_note "pre-apply memory status: ${pre_memory_status}"
  aoa_note "pre-apply protected units: ${pre_protected_units}"
  [[ -f "$game_guard_status" ]] && aoa_note "game guard status: ${game_guard_status}"
  [[ -f "$resource_plan_status" ]] && aoa_note "resource plan status: ${resource_plan_status}"
  exit 0
fi

aoa_note "applying staged resource guards via $(describe_apply_action)"
apply_resource_guard_method

status_json > "$post_status"
service_selection_json > "$post_service_selection_status"
capture_runtime_snapshot "$post_podman_stats" "$post_memory_status"
capture_protected_units "$post_protected_units"
post_guard_status="$(json_field "$post_status" "summary.status" || true)"
post_service_selection="$(json_field "$post_service_selection_status" "summary.status" || true)"
post_staged_count="$(python3 - "$post_status" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = payload.get("summary", {})
print(summary.get("staged_not_applied", summary.get("counts", {}).get("staged_not_applied", 0)))
PY
)"
resource_plan_status="$post_resource_plan_status"
read_resource_plan_ok >/dev/null || true

aoa_note "resource guard status after apply: ${post_guard_status:-unknown} staged=${post_staged_count}"
aoa_note "service selection after apply: ${post_service_selection:-unknown}"
aoa_note "pre-apply status: ${pre_status}"
aoa_note "pre-apply service selection: ${pre_service_selection_status}"
aoa_note "pre-apply podman stats: ${pre_podman_stats}"
aoa_note "pre-apply memory status: ${pre_memory_status}"
aoa_note "pre-apply protected units: ${pre_protected_units}"
aoa_note "pre-apply resource plan: ${pre_resource_plan_status}"
aoa_note "post-apply status: ${post_status}"
aoa_note "post-apply service selection: ${post_service_selection_status}"
aoa_note "post-apply podman stats: ${post_podman_stats}"
aoa_note "post-apply memory status: ${post_memory_status}"
aoa_note "post-apply protected units: ${post_protected_units}"
aoa_note "post-apply resource plan: ${post_resource_plan_status}"

if ! protected_units_ok "$post_protected_units"; then
  aoa_die "protected user units degraded after apply; inspect ${post_protected_units}"
fi

if [[ "$post_service_selection" != "ok" ]]; then
  aoa_die "service selection degraded after apply; inspect ${post_service_selection_status}"
fi

if [[ "$post_guard_status" != "applied" ]]; then
  aoa_die "resource guards still not fully applied; inspect ${post_status}"
fi
