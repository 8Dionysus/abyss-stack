#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid


ABYSS_MACHINE = "/usr/local/bin/abyss-machine"


class AdmissionResponseError(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        decision = payload.get("decision", "unknown")
        reasons = payload.get("reasons") or payload.get("blocked_reasons") or payload.get("denied_reasons") or "no reason"
        super().__init__(f"resource admission denied: {decision}: {reasons}")


def state_path() -> Path:
    override = os.environ.get("AOA_OVMS_ADMISSION_STATE")
    if override:
        return Path(override)
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return runtime_dir / "abyss-stack" / "ovms-admission.json"


def run_json(argv: list[str]) -> dict[str, Any]:
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip()[:300] or "invalid JSON response"
        raise RuntimeError(f"resource admission failed: {detail}") from exc
    if completed.returncode != 0 or not payload.get("ok"):
        raise AdmissionResponseError(payload)
    return payload


def write_state(payload: dict[str, str]) -> None:
    path = state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ovms-admission.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def reserve_argv(request_id: str, release_token: str) -> list[str]:
    return [
        ABYSS_MACHINE,
        "resource",
        "admission",
        "reserve",
        "--owner",
        os.environ.get("AOA_OVMS_OWNER", "abyss-stack"),
        "--workload-id",
        os.environ.get("AOA_OVMS_WORKLOAD_ID", "systemd:abyss-ovms.service"),
        "--request-id",
        request_id,
        "--release-token",
        release_token,
        "--activity",
        "foreground",
        "--class",
        "medium",
        "--kind",
        "ai",
        "--latency",
        "interactive",
        "--memory-demand-mib",
        os.environ.get("AOA_OVMS_COLD_LOAD_MIB", "2800"),
        "--estimate-source",
        "ovms_cold_load_measured",
        "--estimate-confidence",
        "measured",
        "--json",
    ]


def admission_wait_seconds() -> float:
    raw = os.environ.get("AOA_OVMS_ADMISSION_WAIT_SEC", "120")
    try:
        return max(0.0, float(raw))
    except ValueError as exc:
        raise RuntimeError("AOA_OVMS_ADMISSION_WAIT_SEC must be numeric") from exc


def read_state() -> dict[str, str] | None:
    path = state_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid admission state retained at {path}") from exc
    if not isinstance(state, dict):
        raise RuntimeError(f"invalid admission state retained at {path}")
    return {str(key): str(value) for key, value in state.items()}


def release() -> None:
    path = state_path()
    state = read_state()
    if state is None:
        return

    lease_id = str(state.get("lease_id") or "")
    request_id = str(state.get("request_id") or "")
    release_token = str(state.get("release_token") or "")
    if not request_id or not release_token:
        raise RuntimeError(f"incomplete admission state retained at {path}")

    if not lease_id:
        payload = run_json(reserve_argv(request_id, release_token))
        lease_id = str(payload.get("lease", {}).get("id") or "")
        if not lease_id:
            raise RuntimeError("resource admission replay returned no lease")
        state["lease_id"] = lease_id
        state["phase"] = "reserved"
        write_state(state)

    run_json(
        [
            ABYSS_MACHINE,
            "resource",
            "admission",
            "release",
            "--lease-id",
            lease_id,
            "--release-token",
            release_token,
            "--json",
        ]
    )
    path.unlink(missing_ok=True)


def reserve() -> None:
    release()
    request_id = f"ovms-{uuid.uuid4().hex}"
    release_token = secrets.token_urlsafe(32)
    write_state(
        {
            "phase": "pending",
            "request_id": request_id,
            "release_token": release_token,
        }
    )
    deadline = time.monotonic() + admission_wait_seconds()
    delay = 0.5
    while True:
        try:
            payload = run_json(reserve_argv(request_id, release_token))
            break
        except AdmissionResponseError as exc:
            retryable = bool(
                exc.payload.get("decision") == "force_required"
                or exc.payload.get("blocked_reasons")
            )
            remaining = deadline - time.monotonic()
            if not retryable or remaining <= 0:
                state_path().unlink(missing_ok=True)
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2.0, 5.0)
    lease_id = str(payload.get("lease", {}).get("id") or "")
    if not lease_id:
        raise RuntimeError("resource admission returned no releasable lease")
    write_state(
        {
            "phase": "reserved",
            "request_id": request_id,
            "lease_id": lease_id,
            "release_token": release_token,
        }
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"reserve", "release"}:
        print("usage: aoa-ovms-admission {reserve|release}", file=sys.stderr)
        return 2
    try:
        reserve() if sys.argv[1] == "reserve" else release()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"ovms cold-load admission {sys.argv[1]}: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
