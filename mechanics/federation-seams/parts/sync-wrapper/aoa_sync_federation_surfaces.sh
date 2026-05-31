#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)"
# shellcheck source=scripts/aoa-lib.sh
source "${REPO_ROOT}/scripts/aoa-lib.sh"

command -v python3 >/dev/null 2>&1 || aoa_die "python3 is required"

layers=()
check_mode=0
json_mode=0
while (($#)); do
  case "$1" in
    --check)
      check_mode=1
      ;;
    --json)
      json_mode=1
      ;;
    --layer)
      shift || true
      (($#)) || aoa_die "missing value after --layer"
      layers+=("$1")
      ;;
    --layer=*)
      layers+=("${1#*=}")
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
  done

(( ${#layers[@]} > 0 )) || aoa_die "expected --layer"

if (( json_mode )) && ! (( check_mode )); then
  aoa_die "--json requires --check"
fi

emit_check_json() {
  local layer="$1"
  local status="$2"
  local source_root="$3"
  local mirror_target="$4"
  shift 4
  python3 - "$layer" "$status" "$source_root" "$mirror_target" "$@" <<'PY'
from pathlib import Path
import json
import sys

layer = sys.argv[1]
status = sys.argv[2]
source_root = str(Path(sys.argv[3]))
mirror_target = str(Path(sys.argv[4]))
missing_files = [str(Path(item)) for item in sys.argv[5:]]

print(
    json.dumps(
        {
            "layer": layer,
            "status": status,
            "source_root": source_root,
            "mirror_target": mirror_target,
            "missing_files": missing_files,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
)
PY
}

resolve_federation_config_dir() {
  local source_templates_dir runtime_configs_dir
  source_templates_dir="${REPO_ROOT}/config-templates/Configs/federation"
  runtime_configs_dir="${AOA_CONFIGS_ROOT}/federation"

  if [[ -d "${source_templates_dir}" ]]; then
    printf '%s\n' "${source_templates_dir}"
    return 0
  fi
  if [[ -d "${runtime_configs_dir}" ]]; then
    printf '%s\n' "${runtime_configs_dir}"
    return 0
  fi
  aoa_die "federation config directory not found"
}

load_required_paths() {
  local config_path="$1"
  python3 - "$config_path" <<'PY'
from pathlib import Path
import sys

import yaml

config_path = Path(sys.argv[1])
payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
required_files = payload.get("required_files")
if not isinstance(required_files, list) or not required_files:
    raise SystemExit(f"required_files missing or empty in {config_path}")
for rel_path in required_files:
    if not isinstance(rel_path, str) or not rel_path:
        raise SystemExit(f"invalid required_files entry in {config_path}: {rel_path!r}")
    print(rel_path)
PY
}

load_bridge_runtime_evidence_refs() {
  local config_dir="$1"
  python3 - "$config_dir/upstream-compatibility-bridge.json" <<'PY'
from pathlib import Path
import json
import sys

bridge_path = Path(sys.argv[1])
payload = json.loads(bridge_path.read_text(encoding="utf-8"))
templates = payload.get("runtime_evidence_templates")
if not isinstance(templates, dict):
    raise SystemExit(f"runtime_evidence_templates missing or invalid in {bridge_path}")
for name, template in templates.items():
    if not isinstance(template, dict):
        raise SystemExit(f"invalid runtime evidence template bridge entry: {name!r}")
    upstream_ref = template.get("upstream_source_ref")
    if not isinstance(upstream_ref, str) or not upstream_ref:
        raise SystemExit(f"upstream_source_ref missing for runtime evidence template bridge entry: {name}")
    print(upstream_ref)
PY
}

resolve_layer_source_rel() {
  local layer="$1"
  local rel_path="$2"
  if [[ "$layer" == "aoa-evals" ]]; then
    case "$rel_path" in
      docs/TRACE_EVAL_BRIDGE.md)
        printf '%s\n' "mechanics/audit/parts/artifact-verdict-hooks/docs/TRACE_EVAL_BRIDGE.md"
        return 0
        ;;
      docs/RUNTIME_BENCH_PROMOTION_GUIDE.md)
        printf '%s\n' "mechanics/audit/parts/selected-evidence-packets/docs/RUNTIME_BENCH_PROMOTION_GUIDE.md"
        return 0
        ;;
      docs/SELF_AGENT_CHECKPOINT_EVAL_POSTURE.md)
        printf '%s\n' "mechanics/checkpoint/parts/self-agent-posture/docs/SELF_AGENT_CHECKPOINT_EVAL_POSTURE.md"
        return 0
        ;;
      docs/RECURRENCE_PROOF_PROGRAM.md)
        printf '%s\n' "mechanics/recurrence/docs/RECURRENCE_PROOF_PROGRAM.md"
        return 0
        ;;
      generated/runtime_candidate_template_index.min.json)
        printf '%s\n' "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_template_index.min.json"
        return 0
        ;;
      generated/runtime_candidate_intake.min.json)
        printf '%s\n' "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_intake.min.json"
        return 0
        ;;
      examples/runtime_evidence_selection.*.example.json)
        printf '%s\n' "mechanics/audit/parts/selected-evidence-packets/examples/${rel_path#examples/}"
        return 0
        ;;
      examples/artifact_to_verdict_hook.long-horizon-model-tier-orchestra.example.json)
        printf '%s\n' "mechanics/audit/parts/artifact-verdict-hooks/examples/${rel_path#examples/}"
        return 0
        ;;
      examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json)
        printf '%s\n' "mechanics/checkpoint/parts/self-agent-posture/examples/${rel_path#examples/}"
        return 0
        ;;
      examples/artifact_to_verdict_hook.restartable-inquiry-loop.example.json)
        printf '%s\n' "mechanics/checkpoint/parts/restartable-inquiry/examples/${rel_path#examples/}"
        return 0
        ;;
      schemas/runtime-evidence-selection.schema.json)
        printf '%s\n' "mechanics/audit/parts/selected-evidence-packets/schemas/${rel_path#schemas/}"
        return 0
        ;;
      schemas/artifact-to-verdict-hook.schema.json)
        printf '%s\n' "mechanics/audit/parts/artifact-verdict-hooks/schemas/${rel_path#schemas/}"
        return 0
        ;;
      schemas/runtime-candidate-template-index.schema.json)
        printf '%s\n' "mechanics/audit/parts/candidate-readers/schemas/${rel_path#schemas/}"
        return 0
        ;;
    esac
  fi
  printf '%s\n' "$rel_path"
}

write_mirror_manifest() {
  local layer="$1"
  local source_root="$2"
  local target_root="$3"
  local tmp_root="$4"
  shift 4
  python3 - "$layer" "$source_root" "$target_root" "$tmp_root" "$@" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys


layer = sys.argv[1]
source_root = Path(sys.argv[2])
target_root = Path(sys.argv[3])
tmp_root = Path(sys.argv[4])
required_files = [Path(item).as_posix() for item in sys.argv[5:]]


def read_json(rel: str) -> object | None:
    path = tmp_root / rel
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def count_records(payload: object, key: str) -> int | None:
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return len(payload[key])
    if isinstance(payload, list):
        return len(payload)
    return None


def git_commit(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", root.as_posix(), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


file_digests: dict[str, str] = {}
for rel in required_files:
    path = tmp_root / rel
    if path.is_file():
        file_digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

catalog = read_json("generated/eval_catalog.min.json")
template_index = read_json("generated/runtime_candidate_template_index.min.json")
intake = read_json("generated/runtime_candidate_intake.min.json")
manifest = {
    "schema": "abyss_stack_federation_mirror_manifest_v1",
    "layer": layer,
    "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "source_root": source_root.as_posix(),
    "target_root": target_root.as_posix(),
    "source_git_commit": git_commit(source_root),
    "required_file_count": len(required_files),
    "required_files": required_files,
    "file_sha256": file_digests,
    "catalog_count": count_records(catalog, "evals"),
    "runtime_candidate_template_count": count_records(template_index, "templates"),
    "runtime_candidate_intake_count": count_records(intake, "templates"),
    "mirror_is_authority": False,
    "refresh_command": "scripts/aoa-sync-federation-surfaces --layer " + layer,
}
manifest_path = tmp_root / "manifest" / "federation_mirror_manifest.json"
manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
PY
}

sync_layer() {
  local layer="$1"
  local source_root target_root tmp_root src_path rel_path source_rel_path config_dir config_path
  local -a required_paths=()

  command -v rsync >/dev/null 2>&1 || aoa_die "rsync is required"

  case "$layer" in
    aoa-agents)
      source_root="${AOA_AGENTS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents"
      ;;
    aoa-routing)
      source_root="${AOA_ROUTING_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing"
      ;;
    aoa-memo)
      source_root="${AOA_MEMO_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo"
      ;;
    aoa-evals)
      source_root="${AOA_EVALS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"
      ;;
    aoa-playbooks)
      source_root="${AOA_PLAYBOOKS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks"
      ;;
    aoa-kag)
      source_root="${AOA_KAG_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag"
      ;;
    tos-source)
      source_root="${AOA_TOS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/tos-source"
      ;;
    *)
      aoa_die "unsupported layer: ${layer}"
      ;;
  esac

  [[ -d "$source_root" ]] || aoa_die "${layer} root not found: ${source_root}"

  config_dir="$(resolve_federation_config_dir)"
  config_path="${config_dir}/${layer}.yaml"
  [[ -f "$config_path" ]] || aoa_die "federation config not found for ${layer}: ${config_path}"
  while IFS= read -r rel_path; do
    required_paths+=("${rel_path}")
  done < <(load_required_paths "${config_path}")
  if [[ "$layer" == "aoa-evals" ]]; then
    while IFS= read -r rel_path; do
      required_paths+=("${rel_path}")
    done < <(load_bridge_runtime_evidence_refs "${config_dir}")
  fi
  (( ${#required_paths[@]} > 0 )) || aoa_die "no required_files found in ${config_path}"

  if [[ "$layer" == "aoa-agents" ]]; then
    local artifact_schema_count=0
    for rel_path in "${required_paths[@]}"; do
      if [[ "$(basename -- "$rel_path")" == artifact.*.schema.json ]]; then
        artifact_schema_count=$((artifact_schema_count + 1))
      fi
    done
    ((artifact_schema_count > 0)) || aoa_die "no artifact schemas found in aoa-agents federation required paths"
  fi

  aoa_note "layer: ${layer}"
  aoa_note "source root: ${source_root}"
  aoa_note "mirror target: ${target_root}"

  tmp_root="$(mktemp -d)"
  trap 'rm -rf "${tmp_root}"' RETURN

  for rel_path in "${required_paths[@]}"; do
    source_rel_path="$(resolve_layer_source_rel "${layer}" "${rel_path}")"
    src_path="${source_root}/${source_rel_path}"
    [[ -f "$src_path" ]] || aoa_die "required source file missing: ${src_path}"
    mkdir -p "${tmp_root}/$(dirname -- "${rel_path}")"
    cp -a "${src_path}" "${tmp_root}/${rel_path}"
  done
  write_mirror_manifest "${layer}" "${source_root}" "${target_root}" "${tmp_root}" "${required_paths[@]}"

  mkdir -p "$(dirname -- "${target_root}")"
  rsync -a --delete "${tmp_root}/" "${target_root}/"
  rm -rf "${tmp_root}"
  trap - RETURN

  aoa_note "federation surface sync complete for ${layer}"
}

check_layer() {
  local layer="$1"
  local source_root target_root rel_path source_rel_path config_dir config_path
  local -a required_paths=()
  local -a missing_paths=()

  case "$layer" in
    aoa-agents)
      source_root="${AOA_AGENTS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents"
      ;;
    aoa-routing)
      source_root="${AOA_ROUTING_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing"
      ;;
    aoa-memo)
      source_root="${AOA_MEMO_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo"
      ;;
    aoa-evals)
      source_root="${AOA_EVALS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"
      ;;
    aoa-playbooks)
      source_root="${AOA_PLAYBOOKS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks"
      ;;
    aoa-kag)
      source_root="${AOA_KAG_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag"
      ;;
    tos-source)
      source_root="${AOA_TOS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/tos-source"
      ;;
    *)
      aoa_die "unsupported layer: ${layer}"
      ;;
  esac

  [[ -d "$source_root" ]] || aoa_die "${layer} root not found: ${source_root}"

  config_dir="$(resolve_federation_config_dir)"
  config_path="${config_dir}/${layer}.yaml"
  [[ -f "$config_path" ]] || aoa_die "federation config not found for ${layer}: ${config_path}"
  while IFS= read -r rel_path; do
    required_paths+=("${rel_path}")
  done < <(load_required_paths "${config_path}")
  if [[ "$layer" == "aoa-evals" ]]; then
    while IFS= read -r rel_path; do
      required_paths+=("${rel_path}")
    done < <(load_bridge_runtime_evidence_refs "${config_dir}")
  fi
  (( ${#required_paths[@]} > 0 )) || aoa_die "no required_files found in ${config_path}"

  if (( ! json_mode )); then
    aoa_note "check layer: ${layer}"
    aoa_note "source root: ${source_root}"
    aoa_note "mirror target: ${target_root}"
  fi

  for rel_path in "${required_paths[@]}"; do
    source_rel_path="$(resolve_layer_source_rel "${layer}" "${rel_path}")"
    [[ -f "${source_root}/${source_rel_path}" ]] || aoa_die "required source file missing: ${source_root}/${source_rel_path}"
    if [[ ! -f "${target_root}/${rel_path}" ]]; then
      missing_paths+=("${target_root}/${rel_path}")
    fi
  done

  if (( ${#missing_paths[@]} > 0 )); then
    if (( json_mode )); then
      emit_check_json "${layer}" "missing" "${source_root}" "${target_root}" "${missing_paths[@]}"
    else
      printf 'warning: missing mirrored files for %s:\n' "${layer}" >&2
      for rel_path in "${missing_paths[@]}"; do
        printf '  %s\n' "${rel_path}"
      done
    fi
    return 1
  fi

  if (( json_mode )); then
    emit_check_json "${layer}" "ok" "${source_root}" "${target_root}"
  else
    aoa_note "federation surface check complete for ${layer}"
  fi
  return 0
}

overall_status=0
for layer in "${layers[@]}"; do
  if (( check_mode )); then
    if ! check_layer "$layer"; then
      overall_status=1
    fi
  else
    sync_layer "$layer"
  fi
done

exit "${overall_status}"
