#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

command -v rsync >/dev/null 2>&1 || aoa_die "rsync is required"

managed_items=(
  compose
  config-templates
  docs
  mechanics
  mcp
  quests
  scripts
  schemas
  stats
  systemd
  env
  README.md
  QUESTBOOK.md
  CHARTER.md
  BOUNDARIES.md
  DESIGN.md
  DESIGN.AGENTS.md
  ROADMAP.md
  AGENTS.md
)

delete_mode=0
dry_run=0
selected_items=()
syncs_abyss_stack_mcp=0
abyss_stack_mcp_projection_lock_fd=""
source_revision=""
protocol_watch_only=0
protocol_watch_lock_fd=""
protocol_watch_source_revision=""
protocol_watch_files=(
  mcp/protocol-lab/CONTRACT.md
  mcp/protocol-lab/README.md
  mcp/protocol-lab/VALIDATION.md
  mcp/protocol-lab/protocol-watch-plan.v1.json
  mcp/protocol-lab/schemas/protocol-watch-plan.schema.json
  mcp/protocol-lab/schemas/protocol-watch-status.schema.json
  mcp/protocol-lab/scripts/protocol_watcher.py
  mcp/protocol-lab/scripts/validate_protocol_lab.py
  mcp/protocol-lab/tests/test_protocol_watcher.py
  systemd/user/README.md
  systemd/user/abyss-mcp-protocol-watch.service
)

aoa_verify_mcp_source_snapshot() {
  local observed_revision
  observed_revision="$(git -C "$SOURCE_ROOT" rev-parse --verify HEAD)"
  [[ "$observed_revision" == "$source_revision" ]] || \
    aoa_die "MCP deployment source revision changed during synchronization"
  if [[ -n "$(git -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
    aoa_die "MCP deployment source worktree changed during synchronization"
  fi
}

aoa_verify_protocol_watch_source_snapshot() {
  local observed_revision
  if ! observed_revision="$(git -C "$SOURCE_ROOT" rev-parse --verify HEAD)"; then
    aoa_die "protocol-watch deployment requires a Git source checkout"
  fi
  [[ "$observed_revision" == "$protocol_watch_source_revision" ]] || \
    aoa_die "protocol-watch deployment source revision changed during synchronization"
  if [[ -n "$(git -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
    aoa_die "protocol-watch deployment source worktree must be clean"
  fi
}

aoa_protocol_watch_validate_parent_chain() {
  local root="$1"
  local relative="$2"
  local create_missing="$3"
  local relative_parent="${relative%/*}"
  local current="$root"
  local component
  local next
  local -a components=()

  [[ -d "$root" && ! -L "$root" ]] || \
    aoa_die "protocol-watch deployment root must be a non-symlink directory: $root"
  [[ "$relative_parent" != "$relative" ]] || return 0
  IFS='/' read -r -a components <<< "$relative_parent"
  for component in "${components[@]}"; do
    [[ -n "$component" && "$component" != "." && "$component" != ".." ]] || \
      aoa_die "protocol-watch deployment path is unsafe: $relative"
    next="${current}/${component}"
    if [[ -e "$next" || -L "$next" ]]; then
      [[ -d "$next" && ! -L "$next" ]] || \
        aoa_die "protocol-watch deployment parent must be a non-symlink directory: $next"
    elif ((create_missing)); then
      install -d -m 0750 -- "$next"
    fi
    current="$next"
  done
}

aoa_protocol_watch_validate_paths() {
  local relative
  local source_path
  local target_path

  for relative in "${protocol_watch_files[@]}"; do
    source_path="${SOURCE_ROOT}/${relative}"
    [[ -f "$source_path" && ! -L "$source_path" ]] || \
      aoa_die "protocol-watch source allowlist entry must be a regular non-symlink file: $relative"
    target_path="${AOA_CONFIGS_ROOT}/${relative}"
    aoa_protocol_watch_validate_parent_chain "$AOA_CONFIGS_ROOT" "$relative" 0
    if [[ -e "$target_path" || -L "$target_path" ]]; then
      [[ -f "$target_path" && ! -L "$target_path" ]] || \
        aoa_die "protocol-watch target allowlist entry must be a regular non-symlink file: $relative"
    fi
  done
}

aoa_protocol_watch_prepare_lock() {
  local lock_root="${AOA_STACK_ROOT%/}/Logs/mcp/protocol-watch"
  local lock_path="${lock_root}/.lock"
  local lock_owner
  local state_owner
  local current_uid

  [[ -d "$lock_root" && ! -L "$lock_root" ]] || \
    aoa_die "protocol-watch state root must be a non-symlink directory: $lock_root"
  [[ -f "$lock_path" && ! -L "$lock_path" ]] || \
    aoa_die "protocol-watch state lock must be an existing regular non-symlink file: $lock_path"
  lock_owner="$(stat -c '%u' -- "$lock_path")" || \
    aoa_die "cannot inspect protocol-watch state lock owner: $lock_path"
  current_uid="$(id -u)"
  state_owner="$(stat -c '%u' -- "$lock_root")" || \
    aoa_die "cannot inspect protocol-watch state root owner: $lock_root"
  [[ "$state_owner" == "$current_uid" ]] || \
    aoa_die "protocol-watch state root is not owned by the invoking user: $lock_root"
  [[ "$lock_owner" == "$current_uid" ]] || \
    aoa_die "protocol-watch state lock is not owned by the invoking user: $lock_path"
  exec {protocol_watch_lock_fd}<> "$lock_path"
  if ! /usr/bin/flock --exclusive --nonblock "$protocol_watch_lock_fd"; then
    aoa_die "protocol watcher is active; protocol-watch deployment lock is busy"
  fi
}

aoa_protocol_watch_write_receipt() {
  local receipt_files
  receipt_files="$(printf '%s\n' "${protocol_watch_files[@]}")"
  AOA_PROTOCOL_WATCH_SOURCE_ROOT="$SOURCE_ROOT" \
  AOA_PROTOCOL_WATCH_CONFIGS_ROOT="$AOA_CONFIGS_ROOT" \
  AOA_PROTOCOL_WATCH_STACK_ROOT="$AOA_STACK_ROOT" \
  AOA_PROTOCOL_WATCH_SOURCE_REVISION="$protocol_watch_source_revision" \
  AOA_PROTOCOL_WATCH_FILES="$receipt_files" \
    python3 - <<'PY'
import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path


source_root = Path(os.environ["AOA_PROTOCOL_WATCH_SOURCE_ROOT"])
configs_root = Path(os.environ["AOA_PROTOCOL_WATCH_CONFIGS_ROOT"])
stack_root = Path(os.environ["AOA_PROTOCOL_WATCH_STACK_ROOT"])
source_revision = os.environ["AOA_PROTOCOL_WATCH_SOURCE_REVISION"]
relative_files = tuple(
    item for item in os.environ["AOA_PROTOCOL_WATCH_FILES"].splitlines() if item
)


def regular_file(path: Path, label: str) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise SystemExit(f"protocol-watch {label} must be a regular non-symlink file: {path}")


files = []
for relative in relative_files:
    source = source_root / relative
    target = configs_root / relative
    regular_file(source, "source allowlist entry")
    regular_file(target, "deployed allowlist entry")
    source_bytes = source.read_bytes()
    target_bytes = target.read_bytes()
    if source_bytes != target_bytes:
        raise SystemExit(f"protocol-watch deployed file differs after sync: {relative}")
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    target_digest = hashlib.sha256(target_bytes).hexdigest()
    files.append(
        {
            "path": relative,
            "bytes": len(source_bytes),
            "source_sha256": source_digest,
            "deployed_sha256": target_digest,
        }
    )

receipt_root = stack_root / "Logs" / "mcp" / "protocol-watch" / "deployments"
records_root = receipt_root / "records"
for directory in (receipt_root, records_root):
    if directory.exists() or directory.is_symlink():
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SystemExit(f"protocol-watch deployment receipt directory is unsafe: {directory}")
    else:
        directory.mkdir(mode=0o750)

body = {
    "schema_version": "abyss_mcp_protocol_watch_deployment_receipt_v1",
    "owner": "abyss-stack",
    "scope": "protocol-watch-only",
    "whole_stack_projection_claim": False,
    "source_revision": source_revision,
    "parity_state": "exact",
    "runtime_observation_state": "not_observed",
    "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "files": list(files),
}
encoded = (
    json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    + "\n"
).encode("utf-8")
record_digest = hashlib.sha256(encoded).hexdigest()
record_path = records_root / f"{record_digest}.json"
latest_path = receipt_root / "latest.json"
for path in (record_path, latest_path):
    if path.is_symlink() or (path.exists() and not stat.S_ISREG(path.lstat().st_mode)):
        raise SystemExit(f"protocol-watch deployment receipt path is unsafe: {path}")

with tempfile.NamedTemporaryFile(
    mode="wb", dir=records_root, prefix=".receipt-", suffix=".tmp", delete=False
) as handle:
    temporary_record = Path(handle.name)
    os.fchmod(handle.fileno(), 0o600)
    handle.write(encoded)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary_record, record_path)
with tempfile.NamedTemporaryFile(
    mode="wb", dir=receipt_root, prefix=".latest-", suffix=".tmp", delete=False
) as handle:
    temporary_latest = Path(handle.name)
    os.fchmod(handle.fileno(), 0o600)
    handle.write(encoded)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary_latest, latest_path)
print(f"{record_path}\n{latest_path}")
PY
}

aoa_protocol_watch_only_sync() {
  command -v git >/dev/null 2>&1 || aoa_die "git is required for protocol-watch deployment provenance"
  command -v python3 >/dev/null 2>&1 || aoa_die "python3 is required for protocol-watch deployment receipts"
  [[ "$delete_mode" -eq 0 ]] || \
    aoa_die "protocol-watch-only does not support --delete"
  [[ "${#selected_items[@]}" -eq 0 ]] || \
    aoa_die "protocol-watch-only cannot be combined with --item"
  [[ -d "$AOA_CONFIGS_ROOT" && ! -L "$AOA_CONFIGS_ROOT" ]] || \
    aoa_die "protocol-watch deployment target must be an existing non-symlink directory: $AOA_CONFIGS_ROOT"

  aoa_protocol_watch_prepare_lock
  if ! protocol_watch_source_revision="$(git -C "$SOURCE_ROOT" rev-parse --verify HEAD)"; then
    aoa_die "protocol-watch deployment requires a Git source checkout"
  fi
  [[ "$protocol_watch_source_revision" =~ ^[0-9a-f]{40}$ ]] || \
    aoa_die "protocol-watch deployment requires one exact source commit"
  aoa_verify_protocol_watch_source_snapshot
  aoa_protocol_watch_validate_paths

  aoa_note "protocol-watch-only source root: ${SOURCE_ROOT}"
  aoa_note "protocol-watch-only sync target: ${AOA_CONFIGS_ROOT}"
  aoa_note "protocol-watch-only files: ${#protocol_watch_files[@]}"
  aoa_note "protocol-watch-only source revision: ${protocol_watch_source_revision}"
  if ((dry_run)); then
    local relative
    local source_path
    local target_path
    local action
    for relative in "${protocol_watch_files[@]}"; do
      source_path="${SOURCE_ROOT}/${relative}"
      target_path="${AOA_CONFIGS_ROOT}/${relative}"
      if [[ ! -e "$target_path" ]]; then
        action="create"
      elif cmp -s -- "$source_path" "$target_path"; then
        action="unchanged"
      else
        action="update"
      fi
      aoa_note "protocol-watch-only plan ${action}: ${relative}"
    done
    aoa_note "protocol-watch-only preview complete; no files changed"
    return 0
  fi

  local relative
  local source_path
  local target_path
  for relative in "${protocol_watch_files[@]}"; do
    aoa_protocol_watch_validate_parent_chain "$AOA_CONFIGS_ROOT" "$relative" 1
    source_path="${SOURCE_ROOT}/${relative}"
    target_path="${AOA_CONFIGS_ROOT}/${relative}"
    rsync -a -- "$source_path" "$target_path"
  done
  aoa_verify_protocol_watch_source_snapshot
  aoa_protocol_watch_write_receipt
  aoa_note "protocol-watch-only sync complete; whole-stack projection claim: false"
}

aoa_select_sync_item() {
  local requested="$1"
  local candidate

  for candidate in "${managed_items[@]}"; do
    if [[ "$candidate" == "$requested" ]]; then
      selected_items+=("$requested")
      return 0
    fi
  done
  aoa_die "unknown sync item: ${requested}"
}

while (($#)); do
  case "$1" in
    --delete)
      delete_mode=1
      ;;
    --dry-run)
      dry_run=1
      ;;
    --protocol-watch-only)
      protocol_watch_only=1
      ;;
    --item)
      shift
      (($#)) || aoa_die "missing value after --item"
      aoa_select_sync_item "$1"
      ;;
    --item=*)
      aoa_select_sync_item "${1#*=}"
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

if ((protocol_watch_only)); then
  aoa_protocol_watch_only_sync
  if [[ -n "$protocol_watch_lock_fd" ]]; then
    exec {protocol_watch_lock_fd}>&-
  fi
  exit 0
fi

items=("${managed_items[@]}")
if ((${#selected_items[@]})); then
  items=("${selected_items[@]}")
fi
for item in "${items[@]}"; do
  if [[ "$item" == "mcp" ]]; then
    syncs_abyss_stack_mcp=1
    break
  fi
done

if ((dry_run)); then
  [[ -d "${AOA_CONFIGS_ROOT}" ]] || aoa_die "sync target does not exist for dry-run: ${AOA_CONFIGS_ROOT}"
else
  mkdir -p "${AOA_CONFIGS_ROOT}"
fi

if ((!dry_run && syncs_abyss_stack_mcp)); then
  configs_root_without_trailing_slash="${AOA_CONFIGS_ROOT%/}"
  abyss_stack_mcp_projection_lock_root="$(
    dirname -- "$configs_root_without_trailing_slash"
  )/Services/abyss-stack-mcp"
  abyss_stack_mcp_projection_lock="${abyss_stack_mcp_projection_lock_root}/.source-projection.lock"
  if [[ -e "$abyss_stack_mcp_projection_lock_root" || \
        -L "$abyss_stack_mcp_projection_lock_root" ]]; then
    [[ -d "$abyss_stack_mcp_projection_lock_root" && \
       ! -L "$abyss_stack_mcp_projection_lock_root" ]] || \
      aoa_die "abyss-stack MCP source projection lock root must be a non-symlink directory"
  else
    install -d -m 0750 "$abyss_stack_mcp_projection_lock_root"
  fi
  if [[ -e "$abyss_stack_mcp_projection_lock" || \
        -L "$abyss_stack_mcp_projection_lock" ]]; then
    [[ -f "$abyss_stack_mcp_projection_lock" && \
       ! -L "$abyss_stack_mcp_projection_lock" ]] || \
      aoa_die "abyss-stack MCP source projection lock must be a regular non-symlink file"
  else
    (
      umask 077
      set -o noclobber
      : > "$abyss_stack_mcp_projection_lock"
    ) 2>/dev/null || true
    [[ -f "$abyss_stack_mcp_projection_lock" && \
       ! -L "$abyss_stack_mcp_projection_lock" ]] || \
      aoa_die "failed to create the abyss-stack MCP source projection lock"
  fi
  chmod 0600 "$abyss_stack_mcp_projection_lock"
  exec {abyss_stack_mcp_projection_lock_fd}<> \
    "$abyss_stack_mcp_projection_lock"
  if ! /usr/bin/flock --exclusive --nonblock \
    "$abyss_stack_mcp_projection_lock_fd"; then
    aoa_die "abyss-stack MCP runtime provisioning holds the source projection lock"
  fi
  command -v git >/dev/null 2>&1 || \
    aoa_die "git is required for MCP deployment provenance"
  command -v python3 >/dev/null 2>&1 || \
    aoa_die "python3 is required for MCP deployment provenance"
  source_revision="$(git -C "$SOURCE_ROOT" rev-parse --verify HEAD)"
  [[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || \
    aoa_die "MCP deployment requires one exact source commit"
  aoa_verify_mcp_source_snapshot
fi

rsync_flags=(
  -a
  --exclude=.git/
  --exclude=__pycache__/
  --exclude=.pytest_cache/
  --exclude=.mypy_cache/
  --exclude=.ruff_cache/
  --exclude=.coverage
  --exclude='*.pyc'
)
if ((delete_mode)); then
  rsync_flags+=(--delete)
fi
if ((dry_run)); then
  rsync_flags+=(--dry-run --itemize-changes)
fi

aoa_note "source root: ${SOURCE_ROOT}"
aoa_note "sync target: ${AOA_CONFIGS_ROOT}"
if ((delete_mode)); then
  aoa_note "delete mode: enabled"
else
  aoa_note "delete mode: disabled"
fi
aoa_note "dry-run: $([[ $dry_run -eq 1 ]] && printf enabled || printf disabled)"
aoa_note "selected items: ${items[*]}"

for item in "${items[@]}"; do
  rsync "${rsync_flags[@]}" "${SOURCE_ROOT}/${item}" "${AOA_CONFIGS_ROOT}/"
done

if ((dry_run)); then
  aoa_note "config sync preview complete; no files changed"
else
  if ((syncs_abyss_stack_mcp)); then
    aoa_verify_mcp_source_snapshot
    deployment_manifest_command=(
      python3
      "${MECHANIC_SCRIPT_DIR}/scripts/mcp_deployment_manifest.py"
      --source-root
      "${SOURCE_ROOT}"
      --deployed-root
      "${AOA_CONFIGS_ROOT}"
      --output-root
      "${AOA_STACK_ROOT}/Logs/mcp/deployments"
      --source-revision
      "${source_revision}"
    )
    if ((delete_mode)); then
      deployment_manifest_command+=(--delete-mode)
    fi
    "${deployment_manifest_command[@]}"
  fi
  aoa_note "config sync complete"
fi
if [[ -n "$abyss_stack_mcp_projection_lock_fd" ]]; then
  exec {abyss_stack_mcp_projection_lock_fd}>&-
fi
