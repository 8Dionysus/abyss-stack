#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_STACK_ROOT = Path("/srv/AbyssOS/abyss-stack")
CAPTURED_BY = "scripts/aoa-machine-bridge"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def isoformat_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def compact_command(command: list[str]) -> str:
    return " ".join(command)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bridge_record_entries(records_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(records_root.glob("*/machine-bridge.*.json")):
        record = read_json(path)
        if record is None:
            entries.append(
                {
                    "bridge_id": path.parent.name,
                    "path": str(path),
                    "status": "unreadable",
                    "capture_mode": None,
                    "captured_at": None,
                    "warnings": None,
                }
            )
            continue
        entries.append(
            {
                "bridge_id": record.get("bridge_id", path.parent.name),
                "path": str(path),
                "status": record.get("status"),
                "capture_mode": record.get("capture_mode"),
                "captured_at": record.get("captured_at"),
                "warnings": len(record.get("warnings", [])),
            }
        )
    return entries


def run_json_command(command: list[str], timeout: float = 20.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "command": command,
            "returncode": 127,
            "error": f"{command[0]} not found",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "command": command,
            "returncode": 124,
            "error": "timeout",
        }

    parsed: dict[str, Any] | None = None
    parse_error = None
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
            if isinstance(payload, dict):
                parsed = payload
            else:
                parse_error = "stdout JSON is not an object"
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    result: dict[str, Any] = {
        "ok": completed.returncode == 0 and parsed is not None,
        "command": command,
        "returncode": completed.returncode,
    }
    if parsed is not None:
        result["payload"] = parsed
        result["schema"] = parsed.get("schema")
        result["version"] = parsed.get("version")
        result["generated_at"] = parsed.get("generated_at")
        if isinstance(parsed.get("summary"), dict):
            result["summary"] = parsed.get("summary")
    if completed.returncode != 0:
        result["error"] = (completed.stderr or completed.stdout).strip()[:800]
    elif parse_error:
        result["error"] = parse_error
    return result


def public_path_class(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("/var/lib/abyss-machine/"):
        return "abyss-machine-state"
    if path.startswith("/etc/abyss-machine/"):
        return "abyss-machine-config"
    if path.startswith("/srv/AbyssOS/abyss-stack/Logs/"):
        return "stack-runtime-logs"
    if path.startswith("/srv/AbyssOS/abyss-stack/"):
        return "stack-runtime-root"
    if path.startswith("/home/"):
        return "source-checkout"
    return "local-path"


def maybe_path(path: str | None, capture_mode: str) -> str | None:
    if capture_mode == "private":
        return path
    return None


def artifact_index(stack_bridge: dict[str, Any] | None, capture_mode: str) -> dict[str, Any]:
    artifacts = stack_bridge.get("artifacts") if isinstance(stack_bridge, dict) else None
    if not isinstance(artifacts, dict):
        return {"classes": [], "refs": []}

    refs: list[dict[str, Any]] = []
    for class_name, class_payload in sorted(artifacts.items()):
        if not isinstance(class_payload, dict):
            continue
        for name, ref in sorted(class_payload.items()):
            if not isinstance(ref, dict):
                continue
            raw_path = ref.get("path") if isinstance(ref.get("path"), str) else None
            refs.append(
                {
                    "class": class_name,
                    "name": name,
                    "path": maybe_path(raw_path, capture_mode),
                    "path_class": public_path_class(raw_path),
                    "schema": ref.get("schema"),
                    "truth_level": ref.get("truth_level"),
                }
            )
    return {
        "classes": sorted(artifacts),
        "refs": refs,
    }


def command_catalog(stack_bridge: dict[str, Any] | None) -> dict[str, Any]:
    paths = stack_bridge.get("paths") if isinstance(stack_bridge, dict) else {}
    commands = paths.get("commands") if isinstance(paths, dict) else {}
    if not isinstance(commands, dict):
        commands = {}
    manifest_commands = stack_bridge.get("first_commands") if isinstance(stack_bridge, dict) else None
    return {
        "stack_bridge_commands": commands,
        "first_commands": manifest_commands if isinstance(manifest_commands, list) else [],
        "required_stack_side_commands": [
            "scripts/aoa-machine-bridge --write-latest",
            "scripts/aoa-doctor --preset intel-full",
            "scripts/aoa-machine-fit --mode private --write ${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json",
        ],
    }


def topological_routes(stack_root: Path, capture_mode: str) -> dict[str, Any]:
    logs = stack_root / "Logs" / "machine-bridge"
    return {
        "source_to_runtime": {
            "source_checkout": maybe_path(str(Path.cwd()), capture_mode),
            "deployed_runtime_root": maybe_path(str(stack_root), capture_mode),
            "deployed_configs_root": maybe_path(str(stack_root / "Configs"), capture_mode),
            "rule": "source-authored changes become live only through the deployment bridge; runtime logs are local evidence",
        },
        "machine_to_stack": {
            "host_owner": "abyss-machine",
            "stack_consumer": "abyss-stack",
            "direction": "abyss-stack consumes abyss-machine; abyss-machine does not import or mutate abyss-stack",
            "latest_stack_record": maybe_path(str(logs / "latest" / f"latest.{capture_mode}.json"), capture_mode),
            "history_glob": maybe_path(str(logs / "records" / "YYYY-MM-DDTHHMMSSZ__machine-bridge" / f"machine-bridge.{capture_mode}.json"), capture_mode),
            "index": maybe_path(str(logs / "index.json"), capture_mode),
        },
        "runtime_log_tree": {
            "machine_bridge": "Logs/machine-bridge/",
            "host_facts": "Logs/host-facts/",
            "machine_fit": "Logs/machine-fit/",
            "diagnostics": "Logs/diagnostics/",
            "platform_adaptations": "Logs/platform-adaptations/",
            "runtime_benchmarks": "Logs/runtime-benchmarks/",
        },
    }


def summarize_payload(payload: dict[str, Any] | None, capture_mode: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    summary: dict[str, Any] = {
        "schema": payload.get("schema"),
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "ok": payload.get("ok"),
    }
    if isinstance(payload.get("summary"), dict):
        summary["summary"] = payload.get("summary")
    if "selected_mode" in payload or "effective_mode" in payload:
        summary["mode"] = {
            "selected_mode": payload.get("selected_mode"),
            "effective_mode": payload.get("effective_mode"),
            "reasons": payload.get("reasons"),
        }
    if isinstance(payload.get("launch_policy"), dict):
        launch = payload["launch_policy"]
        summary["launch_policy"] = {
            "max_unattended_class": launch.get("max_unattended_class"),
            "can_start_heavy_unattended": launch.get("can_start_heavy_unattended"),
            "can_start_sustained_unattended": launch.get("can_start_sustained_unattended"),
        }
    if isinstance(payload.get("attention"), list):
        summary["attention"] = payload.get("attention")
    if capture_mode == "private" and isinstance(payload.get("paths"), dict):
        summary["paths"] = payload.get("paths")
    return summary


def build_record(capture_mode: str, stack_root: Path) -> tuple[dict[str, Any], int]:
    now = utc_now()
    abyss_machine_path = shutil.which("abyss-machine")
    commands = {
        "stack_bridge_export": ["abyss-machine", "stack-bridge", "export", "--json"],
        "stack_bridge_validate": ["abyss-machine", "stack-bridge", "validate", "--json"],
        "bridge": ["abyss-machine", "bridge", "--json"],
        "mode_plan": ["abyss-machine", "mode", "plan", "--json"],
        "memory_plan": ["abyss-machine", "memory", "plan", "--json"],
        "resource_status": ["abyss-machine", "resource", "status", "--json"],
        "storage_pressure": ["abyss-machine", "storage", "pressure", "--json"],
        "process_containers": ["abyss-machine", "processes", "containers", "--json"],
        "ai_llm_registry": ["abyss-machine", "ai", "llm", "registry", "--json"],
        "ai_llm_validate": ["abyss-machine", "ai", "llm", "validate", "--json"],
        "nervous_status": ["abyss-machine", "nervous", "status", "--json"],
    }

    results = {
        name: run_json_command(command)
        for name, command in commands.items()
    }
    stack_bridge_payload = results["stack_bridge_export"].get("payload")
    bridge_payload = results["bridge"].get("payload")

    required_ok = bool(abyss_machine_path) and bool(results["stack_bridge_export"].get("ok"))
    validate_ok = bool(results["stack_bridge_validate"].get("ok")) and bool(
        results["stack_bridge_validate"].get("payload", {}).get("ok")
    )
    warnings: list[str] = []
    if not abyss_machine_path:
        warnings.append("abyss-machine command is not available")
    if not required_ok:
        warnings.append("stack bridge export is unavailable")
    if required_ok and not validate_ok:
        warnings.append("stack bridge validation did not return ok")
    for name, result in results.items():
        if name in {"stack_bridge_export", "stack_bridge_validate"}:
            continue
        if not result.get("ok"):
            warnings.append(f"{name} unavailable: {result.get('error') or result.get('returncode')}")

    evidence = {
        name: summarize_payload(result.get("payload"), capture_mode)
        for name, result in results.items()
        if isinstance(result.get("payload"), dict)
    }
    execution = {
        name: {
            "ok": result.get("ok"),
            "returncode": result.get("returncode"),
            "command": compact_command(result.get("command", [])),
            "schema": result.get("schema"),
            "generated_at": result.get("generated_at"),
            "error": result.get("error"),
        }
        for name, result in results.items()
    }

    record = {
        "artifact_kind": "aoa.machine-bridge",
        "schema_version": "1",
        "capture_mode": capture_mode,
        "captured_at": isoformat_z(now),
        "captured_by": CAPTURED_BY,
        "bridge_id": now.strftime("%Y-%m-%dT%H%M%SZ__machine-bridge"),
        "status": "ready" if required_ok and validate_ok and not warnings else "warning" if required_ok else "unavailable",
        "summary": {
            "abyss_machine_available": bool(abyss_machine_path),
            "stack_bridge_export_ok": bool(results["stack_bridge_export"].get("ok")),
            "stack_bridge_validate_ok": validate_ok,
            "warnings": len(warnings),
            "artifact_classes": artifact_index(stack_bridge_payload, capture_mode)["classes"],
        },
        "contract": {
            "machine_owner": "abyss-machine",
            "stack_owner": "abyss-stack",
            "dependency_direction": "abyss-stack may consume abyss-machine; abyss-machine must not import or mutate abyss-stack",
            "stack_side_mutates_machine": False,
            "host_layer_mutates_stack": False,
            "read_only_by_default": True,
            "private_runtime_artifact": capture_mode == "private",
        },
        "topology": topological_routes(stack_root, capture_mode),
        "artifact_index": artifact_index(stack_bridge_payload, capture_mode),
        "command_catalog": command_catalog(stack_bridge_payload),
        "host_bridge": {
            "abyss_machine_binary": maybe_path(abyss_machine_path, capture_mode),
            "bridge_schema": bridge_payload.get("schema") if isinstance(bridge_payload, dict) else None,
            "bridge_version": bridge_payload.get("version") if isinstance(bridge_payload, dict) else None,
            "bridge_command_count": len(bridge_payload.get("commands", {})) if isinstance(bridge_payload, dict) and isinstance(bridge_payload.get("commands"), dict) else None,
            "stack_bridge_summary": stack_bridge_payload.get("summary") if isinstance(stack_bridge_payload, dict) else None,
        },
        "live_evidence": evidence,
        "execution": execution,
        "warnings": warnings,
        "non_claims": [
            "This stack-side bridge does not own or change Abyss Machine.",
            "This stack-side bridge does not start, stop, migrate, throttle, or re-affinitize services or processes.",
            "This stack-side bridge records routing evidence; it does not prove model quality, service correctness, or promotion readiness by itself.",
            "Private captures may contain local paths and process/container names and must not be committed.",
        ],
    }
    if capture_mode == "public":
        record["redaction"] = {
            "local_paths_redacted": True,
            "raw_host_payloads_omitted": True,
            "env_and_create_commands_excluded": True,
        }
    return record, 0 if required_ok else 1


def write_latest_bundle(stack_root: Path, record: dict[str, Any], capture_mode: str) -> dict[str, str]:
    bridge_root = stack_root / "Logs" / "machine-bridge"
    latest_path = bridge_root / "latest" / f"latest.{capture_mode}.json"
    record_dir = bridge_root / "records" / str(record["bridge_id"])
    record_path = record_dir / f"machine-bridge.{capture_mode}.json"
    index_path = bridge_root / "index.json"
    records_root = bridge_root / "records"
    written_paths = {
        "latest": str(latest_path),
        "record": str(record_path),
        "index": str(index_path),
    }

    record["written_paths"] = written_paths
    write_json(latest_path, record)
    write_json(record_path, record)
    index = {
        "artifact_kind": "aoa.machine-bridge.index",
        "schema_version": "1",
        "updated_at": record.get("captured_at"),
        "latest": str(latest_path),
        "latest_record": str(record_path),
        "records_root": str(records_root),
        "records": bridge_record_entries(records_root),
        "capture_mode": capture_mode,
        "status": record.get("status"),
        "summary": record.get("summary"),
        "commands": {
            "capture": "scripts/aoa-machine-bridge --write-latest",
            "check": "scripts/aoa-machine-bridge --check",
            "host_export": "abyss-machine stack-bridge export --json",
            "host_validate": "abyss-machine stack-bridge validate --json",
        },
        "non_claims": [
            "Index points at local runtime evidence and is not a source-owned truth surface.",
            "Do not commit private machine-bridge records.",
        ],
    }
    write_json(index_path, index)
    return written_paths


def check_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_kind": "aoa.machine-bridge.check",
        "schema_version": "1",
        "status": record.get("status"),
        "summary": record.get("summary"),
        "warnings": record.get("warnings", []),
        "non_claims": [
            "Check output is compact and public-safe by default.",
            "Use --write or --write-latest explicitly when a full bridge record is needed.",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture the read-only abyss-machine bridge for abyss-stack.")
    parser.add_argument("--mode", choices=("private", "public"), default="private")
    parser.add_argument("--stack-root", default=os.environ.get("AOA_STACK_ROOT", str(DEFAULT_STACK_ROOT)))
    parser.add_argument("--write", help="Write one artifact to this path instead of stdout.")
    parser.add_argument("--write-latest", action="store_true", help="Write latest, record history, and index under Logs/machine-bridge.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero unless abyss-machine stack-bridge export and validation are available.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    stack_root = Path(args.stack_root)
    record, exit_code = build_record(args.mode, stack_root)

    if args.write_latest:
        write_latest_bundle(stack_root, record, args.mode)

    if args.write:
        write_json(Path(args.write), record)
    elif args.check:
        print(json.dumps(check_summary(record), indent=2, ensure_ascii=False))
    elif not args.write_latest:
        print(json.dumps(record, indent=2, ensure_ascii=False))

    if args.check:
        return 0 if record.get("status") == "ready" else 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
