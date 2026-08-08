#!/usr/bin/env python3
"""Detect MCP pair drift and run a removable, explicitly configured lab suite.

The watcher is deliberately protocol-lab orchestration, not production
lifecycle authority.  A successful run advances only its private last-success
fingerprint.  Production files are measured before and after every suite and
are never written by this process.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = LAB_ROOT / "protocol-watch-plan.v1.json"
DEFAULT_STATE_ROOT = LAB_ROOT / "generated" / "protocol-watch"
USER_AGENT = "os-abyss-mcp-protocol-watcher/1"


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _resolve(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else base / path


def _pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(pointer)
    return current


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(mode)


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_json(path, value, mode=0o600)


def _atomic_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(0o600)


def _immutable_private_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"immutable observation collision: {path}")
    else:
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
    return _digest(payload)


def _tree_record(base: Path, raw_paths: list[str]) -> dict[str, Any]:
    files: list[dict[str, str]] = []
    for raw in raw_paths:
        path = _resolve(base, raw)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"watched tree member is not a regular non-symlink file: {path}")
        files.append({"path": raw, "sha256": _file_digest(path)})
    return {"files": files, "tree_digest": _digest(files)}


def _command_output(argv: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        argv,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def _observe_input(
    item: dict[str, Any],
    *,
    base: Path,
    timeout: int,
    urlopen: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    input_id = item["input_id"]
    kind = item["kind"]
    record: dict[str, Any] = {
        "input_id": input_id,
        "kind": kind,
        "required": item["required"],
        "status": "passed",
    }
    try:
        if kind == "file":
            path = _resolve(base, item["path"])
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"not a regular non-symlink file: {path}")
            record["observation"] = {
                "path": item["path"],
                "sha256": _file_digest(path),
                "size_bytes": path.stat().st_size,
            }
        elif kind == "tree":
            record["observation"] = _tree_record(base, item["paths"])
        elif kind == "executable":
            executable = shutil.which(item["command"])
            if executable is None:
                raise ValueError(f"executable not found: {item['command']}")
            path = Path(executable).resolve(strict=True)
            record["observation"] = {
                "resolved_path": str(path),
                "sha256": _file_digest(path),
                "version": _command_output([str(path), *item["probe_argv"]], timeout),
                "features_sha256": _digest(
                    _command_output([str(path), *item["feature_argv"]], timeout).encode()
                ),
            }
        elif kind == "https_json":
            request = urllib.request.Request(
                item["url"],
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                payload = json.loads(raw)
                selected = {pointer: _pointer(payload, pointer) for pointer in item["select"]}
                record["observation"] = {
                    "url": item["url"],
                    "selected": selected,
                    "selected_digest": _digest(selected),
                    "response_sha256": _digest(raw),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        else:
            raise ValueError(f"unsupported input kind: {kind}")
    except Exception as exc:  # bounded into fail-closed watcher evidence
        record["status"] = "blocked"
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def _input_fingerprints(records: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in records:
        observation = item.get("observation") or {}
        if item["kind"] == "https_json":
            identity = observation.get("selected_digest")
        elif item["kind"] == "executable":
            identity = {
                "sha256": observation.get("sha256"),
                "version": observation.get("version"),
                "features_sha256": observation.get("features_sha256"),
            }
        elif item["kind"] == "tree":
            identity = observation.get("tree_digest")
        else:
            identity = observation.get("sha256")
        result[item["input_id"]] = _digest(
            {
                "kind": item["kind"],
                "required": item["required"],
                "status": item["status"],
                "identity": identity,
            }
        )
    return result


def _fingerprint(records: list[dict[str, Any]]) -> str:
    return _digest(_input_fingerprints(records))


def _ttl(plan: dict[str, Any], base: Path, now: datetime) -> dict[str, Any]:
    source = plan["ttl_source"]
    try:
        payload = _read_json(_resolve(base, source["path"]))
        expires_at = datetime.fromisoformat(
            str(_pointer(payload, source["pointer"])).replace("Z", "+00:00")
        )
        remaining = int((expires_at - now).total_seconds())
        return {
            "status": "passed",
            "expires_at": _timestamp(expires_at),
            "remaining_seconds": remaining,
            "lead_seconds": plan["ttl_lead_seconds"],
            "refresh_due": remaining <= plan["ttl_lead_seconds"],
        }
    except Exception as exc:
        return {"status": "blocked", "error": f"{type(exc).__name__}: {exc}", "refresh_due": True}


def _load_protocol_status(plan: dict[str, Any], base: Path) -> dict[str, Any]:
    source = plan["ttl_source"]
    return _read_json(_resolve(base, source["path"]))


def _verdicts(
    protocol_status: dict[str, Any] | None,
    *,
    observation_ready: bool,
) -> dict[str, bool]:
    status = protocol_status or {}
    blockers = set(status.get("production_cutover_blockers", []))
    reasons = set(status.get("reason_codes", []))
    read_allowed = bool(status.get("read_only_pilot_allowed", False))
    core_allowed = bool(status.get("core_read_migration_allowed", False))
    return {
        "compatible_for_lab": observation_ready and read_allowed,
        "eligible_for_read_canary": observation_ready and read_allowed,
        "eligible_for_core_read": observation_ready and core_allowed,
        "blocked_on_conformance": "current_conformance_fixture_mismatch" in blockers,
        "blocked_on_cancellation": "modern_cancellation_not_propagated" in blockers,
        "blocked_on_auth": any("auth" in item for item in blockers),
        "client_extension_capability_absent": "tasks_client_extension_capability_absent" in reasons,
        "production_cutover_allowed": observation_ready and core_allowed,
    }


def _private_secret(path: Path) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"secret is not a regular non-symlink file: {path}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError(f"secret must be mode 0600: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise ValueError(f"secret is missing or too short: {path}")
    return value


def _expand(value: str, run_root: Path) -> str:
    return value.replace("{run_root}", str(run_root))


def _measure_paths(raw_paths: list[str], run_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in raw_paths:
        path = Path(_expand(raw, run_root)).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"protected path is not a regular non-symlink file: {path}")
        result[str(path)] = _file_digest(path)
    return result


def _execute_suite(
    runtime: dict[str, Any],
    *,
    run_root: Path,
) -> tuple[bool, bool, list[dict[str, Any]], list[str]]:
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    secret_values: list[str] = []
    failures: list[str] = []
    for name, raw_path in runtime["secret_files"].items():
        value = _private_secret(Path(_expand(raw_path, run_root)).expanduser())
        environment[name] = value
        secret_values.append(value)
    before = _measure_paths(runtime["protected_paths"], run_root)
    step_receipts: list[dict[str, Any]] = []
    suite_passed = True
    for step in runtime["steps"]:
        argv = [_expand(value, run_root) for value in step["argv"]]
        step_environment = dict(environment)
        for name, raw_value in step["environment"].items():
            if any(marker in name for marker in ("TOKEN", "SECRET", "KEY", "CREDENTIAL")):
                raise ValueError(
                    f"step {step['step_id']} must receive secret environment through secret_files"
                )
            step_environment[name] = _expand(raw_value, run_root)
        started = _timestamp()
        try:
            result = subprocess.run(
                argv,
                env=step_environment,
                cwd=run_root,
                capture_output=True,
                timeout=step["timeout_seconds"],
            )
            output = result.stdout + result.stderr
            if any(value.encode() in output for value in secret_values):
                raise RuntimeError("secret material appeared in child output")
            step_log_root = run_root / "step-logs"
            stdout_path = step_log_root / f"{step['step_id']}.stdout"
            stderr_path = step_log_root / f"{step['step_id']}.stderr"
            _atomic_private_bytes(stdout_path, result.stdout)
            _atomic_private_bytes(stderr_path, result.stderr)
            step_receipts.append(
                {
                    "step_id": step["step_id"],
                    "started_at": started,
                    "finished_at": _timestamp(),
                    "argv_sha256": _digest(argv),
                    "returncode": result.returncode,
                    "stdout_sha256": _digest(result.stdout),
                    "stderr_sha256": _digest(result.stderr),
                    "stdout_ref": f"local://{stdout_path}",
                    "stderr_ref": f"local://{stderr_path}",
                }
            )
            if result.returncode != 0:
                suite_passed = False
                failures.append(f"step {step['step_id']} returned {result.returncode}")
                break
        except Exception as exc:
            suite_passed = False
            failures.append(f"step {step['step_id']} failed: {type(exc).__name__}: {exc}")
            break
    after = _measure_paths(runtime["protected_paths"], run_root)
    protected_unchanged = before == after
    if not protected_unchanged:
        suite_passed = False
        failures.append("one or more protected production files changed")
    receipts: list[dict[str, Any]] = step_receipts
    if suite_passed:
        for item in runtime["required_receipts"]:
            path = Path(_expand(item["path"], run_root))
            try:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("not a regular non-symlink file")
                if item["visibility"] == "private" and stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError("private receipt is not mode 0600")
                encoded = path.read_bytes()
                if any(value.encode() in encoded for value in secret_values):
                    raise ValueError("secret material appeared in receipt")
                receipts.append(
                    {
                        "receipt_id": item["receipt_id"],
                        "visibility": item["visibility"],
                        "path": str(path),
                        "sha256": _digest(encoded),
                        "size_bytes": len(encoded),
                    }
                )
            except Exception as exc:
                suite_passed = False
                failures.append(f"receipt {item['receipt_id']} failed: {type(exc).__name__}: {exc}")
    return suite_passed, protected_unchanged, receipts, failures


def _status_digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "status_digest"}
    return _digest(unsigned)


def _public_safe_status(status: dict[str, Any]) -> dict[str, Any]:
    """Remove machine-local paths and raw errors from the publishable projection."""

    public = dict(status)
    public["private_observation_ref"] = (
        "private://protocol-watch-observation/"
        + status["private_observation_sha256"].removeprefix("sha256:")
    )
    public["inputs"] = [
        {
            "input_id": item["input_id"],
            "kind": item["kind"],
            "required": item["required"],
            "status": item["status"],
            "identity_digest": _digest(item.get("observation", {})),
            **(
                {"error_class": str(item.get("error", "blocked")).split(":", 1)[0]}
                if item["status"] not in {"passed", "skipped"}
                else {}
            ),
        }
        for item in status["inputs"]
    ]
    public["receipts"] = [
        {
            key: value
            for key, value in receipt.items()
            if key
            in {
                "step_id",
                "receipt_id",
                "visibility",
                "returncode",
                "sha256",
                "size_bytes",
                "started_at",
                "finished_at",
                "argv_sha256",
                "stdout_sha256",
                "stderr_sha256",
            }
        }
        for receipt in status["receipts"]
    ]
    failure_codes = [
        f"required_input_blocked:{item['input_id']}"
        for item in status["inputs"]
        if item["required"] and item["status"] != "passed"
    ]
    if status["ttl"].get("status") != "passed":
        failure_codes.append("evidence_ttl_unavailable")
    if status["execution_state"] == "awaiting_runtime_config":
        failure_codes.append("private_runtime_config_unavailable")
    if status["protected_paths_unchanged"] is False:
        failure_codes.append("protected_production_path_changed")
    if status["execution_state"] == "lab_failed":
        failure_codes.append("configured_lab_failed")
    public["failures"] = list(dict.fromkeys(failure_codes))
    public["status_digest"] = _status_digest(public)
    return public


def run(
    *,
    plan_path: Path,
    state_root: Path,
    runtime_config: Path | None,
    execute: bool,
    offline: bool,
    timeout: int,
    now: datetime | None = None,
    urlopen: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    observed_now = now or _now()
    plan = _read_json(plan_path)
    base = plan_path.parent
    if plan.get("schema_version") != "abyss_mcp_protocol_watch_plan_v1":
        raise ValueError("unsupported protocol watch plan schema")
    input_ids = [item["input_id"] for item in plan["inputs"]]
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("protocol watch input_id values must be unique")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    lock_path = state_root / ".lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        records: list[dict[str, Any]] = []
        for item in plan["inputs"]:
            if offline and item["kind"] == "https_json":
                records.append(
                    {
                        "input_id": item["input_id"],
                        "kind": item["kind"],
                        "required": item["required"],
                        "status": "blocked" if item["required"] else "skipped",
                        "error": "offline observation requested",
                    }
                )
            else:
                records.append(
                    _observe_input(item, base=base, timeout=timeout, urlopen=urlopen)
                )
        input_fingerprints = _input_fingerprints(records)
        snapshot_digest = _digest(input_fingerprints)
        observation_ready = not any(
            item["required"] and item["status"] != "passed" for item in records
        )
        ttl = _ttl(plan, base, observed_now)
        observation_path = (
            state_root
            / "observations"
            / (
                observed_now.strftime("%Y%m%dT%H%M%S.%fZ")
                + "-"
                + snapshot_digest.removeprefix("sha256:")[:12]
                + ".json"
            )
        )
        observation_sha256 = _immutable_private_json(
            observation_path,
            {
                "schema_version": "abyss_mcp_protocol_watch_observation_v1",
                "plan_id": plan["plan_id"],
                "observed_at": _timestamp(observed_now),
                "input_snapshot_digest": snapshot_digest,
                "input_fingerprints": input_fingerprints,
                "inputs": records,
                "ttl": ttl,
            },
        )
        if ttl["status"] != "passed":
            observation_ready = False
        previous_path = state_root / "last-success.json"
        previous = _read_json(previous_path) if previous_path.is_file() else None
        previous_digest = previous.get("input_snapshot_digest") if previous else None
        trigger_reasons: list[str] = []
        if previous_digest is None:
            trigger_reasons.append("no_successful_baseline")
        elif previous_digest != snapshot_digest:
            previous_inputs = previous.get("input_fingerprints", {})
            for input_id in sorted(set(previous_inputs) | set(input_fingerprints)):
                if previous_inputs.get(input_id) != input_fingerprints.get(input_id):
                    trigger_reasons.append(f"input_changed:{input_id}")
        if ttl.get("refresh_due"):
            trigger_reasons.append("evidence_ttl_due")
        triggered = bool(trigger_reasons)
        failures = [
            f"input {item['input_id']}: {item.get('error', 'blocked')}"
            for item in records
            if item["required"] and item["status"] != "passed"
        ]
        if ttl["status"] != "passed":
            failures.append(f"ttl: {ttl['error']}")
        try:
            protocol_status = _load_protocol_status(plan, base)
        except Exception as exc:
            protocol_status = None
            observation_ready = False
            failures.append(f"protocol status: {type(exc).__name__}: {exc}")
        execution_state = "trigger_pending" if triggered else "no_change"
        run_id: str | None = None
        protected_unchanged: bool | None = None
        receipts: list[dict[str, Any]] = []
        suite_passed = False
        if not observation_ready:
            execution_state = "observation_blocked"
        elif triggered and execute:
            if runtime_config is None or not runtime_config.is_file():
                execution_state = "awaiting_runtime_config"
                failures.append("private runtime config is unavailable")
            else:
                info = runtime_config.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("runtime config must be a regular non-symlink file")
                if stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError("runtime config must be mode 0600")
                runtime = _read_json(runtime_config)
                if runtime.get("schema_version") != "abyss_mcp_protocol_watch_runtime_v1":
                    raise ValueError("unsupported protocol watch runtime schema")
                run_id = observed_now.strftime("%Y%m%dT%H%M%S.%fZ")
                run_root = state_root / "runs" / run_id
                run_root.mkdir(parents=True, mode=0o700)
                _atomic_private_json(
                    run_root / "input-snapshot.json",
                    {
                        "observed_at": _timestamp(observed_now),
                        "input_snapshot_digest": snapshot_digest,
                        "inputs": records,
                        "ttl": ttl,
                    },
                )
                suite_passed, protected_unchanged, receipts, suite_failures = _execute_suite(
                    runtime,
                    run_root=run_root,
                )
                failures.extend(suite_failures)
                execution_state = "lab_passed" if suite_passed else "lab_failed"
                _atomic_private_json(
                    run_root / "execution-receipt.json",
                    {
                        "run_id": run_id,
                        "passed": suite_passed,
                        "protected_paths_unchanged": protected_unchanged,
                        "receipts": receipts,
                        "failures": suite_failures,
                    },
                )
        status: dict[str, Any] = {
            "schema_version": "abyss_mcp_protocol_watch_status_v1",
            "plan_id": plan["plan_id"],
            "observed_at": _timestamp(observed_now),
            "input_snapshot_digest": snapshot_digest,
            "private_observation_ref": f"local://{observation_path}",
            "private_observation_sha256": observation_sha256,
            "previous_success_digest": previous_digest,
            "observation_ready": observation_ready,
            "triggered": triggered,
            "trigger_reasons": trigger_reasons,
            "execution_state": execution_state,
            "run_id": run_id,
            "inputs": records,
            "ttl": ttl,
            "verdicts": _verdicts(protocol_status, observation_ready=observation_ready),
            "production_automatically_changed": False,
            "protected_paths_unchanged": protected_unchanged,
            "receipts": receipts,
            "failures": failures,
            "claim_limits": plan["claim_limits"],
        }
        status["status_digest"] = _status_digest(status)
        _atomic_private_json(state_root / "current.json", status)
        _atomic_json(
            state_root / "public-safe.json",
            _public_safe_status(status),
            mode=0o644,
        )
        if suite_passed:
            _atomic_private_json(
                previous_path,
                {
                    "schema_version": "abyss_mcp_protocol_watch_success_v1",
                    "accepted_at": _timestamp(),
                    "input_snapshot_digest": snapshot_digest,
                    "input_fingerprints": input_fingerprints,
                    "run_id": run_id,
                    "receipts": receipts,
                },
            )
        return status
    finally:
        os.close(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    status = run(
        plan_path=args.plan.resolve(),
        state_root=args.state_root.resolve(),
        runtime_config=args.runtime_config.resolve() if args.runtime_config else None,
        execute=args.execute,
        offline=args.offline,
        timeout=args.timeout,
    )
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status["execution_state"] not in {"observation_blocked", "lab_failed"} else 1


if __name__ == "__main__":
    sys.exit(main())
