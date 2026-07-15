#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.request
import uuid


MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024


class AdmissionError(RuntimeError):
    pass


def admission_request(path: Path, payload: dict[str, Any], timeout_sec: float) -> dict[str, Any]:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_REQUEST_BYTES:
        raise AdmissionError("request_too_large")

    chunks: list[bytes] = []
    received = 0
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout_sec)
            client.connect(os.fspath(path))
            client.sendall(encoded)
            client.shutdown(socket.SHUT_WR)
            while True:
                chunk = client.recv(min(65536, MAX_RESPONSE_BYTES + 1 - received))
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if received > MAX_RESPONSE_BYTES:
                    raise AdmissionError("response_too_large")
    except OSError as exc:
        raise AdmissionError(f"transport_{type(exc).__name__}") from exc

    try:
        response = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdmissionError("response_invalid") from exc
    if not isinstance(response, dict):
        raise AdmissionError("response_not_object")
    return response


def reserve(args: argparse.Namespace, interrupted: Callable[[], bool]) -> tuple[str, str]:
    request_id = f"llama-swap-{uuid.uuid4().hex}"
    release_token = secrets.token_urlsafe(32)
    payload = {
        "command": "reserve",
        "request": {
            "operation": "cold_load",
            "owner": args.owner,
            "workload_id": args.workload_id,
            "request_id": request_id,
            "release_token": release_token,
            "activity": args.activity,
            "class": args.workload_class,
            "kind": args.kind,
            "latency": args.latency,
            "memory_demand_mib": args.memory_demand_mib,
            "estimate_source": args.estimate_source,
            "estimate_confidence": args.estimate_confidence,
        },
    }
    deadline = time.monotonic() + max(0.0, args.admission_wait)
    delay = 0.5
    last_error = "not_allowed"

    while True:
        if interrupted():
            raise AdmissionError("reservation_cancelled")
        try:
            response = admission_request(args.socket, payload, args.admission_timeout)
        except AdmissionError as exc:
            last_error = str(exc)
            retryable = last_error.startswith("transport_")
        else:
            lease = response.get("lease") if isinstance(response.get("lease"), dict) else {}
            lease_id = str(lease.get("id") or "")
            if response.get("ok") is True and response.get("decision") == "allow" and lease_id:
                return lease_id, release_token
            reasons = response.get("denied_reasons") or response.get("blocked_reasons") or ["not_allowed"]
            last_error = f"{response.get('decision') or 'invalid'}:" + ",".join(str(item) for item in reasons)
            retryable = response.get("decision") == "force_required"

        remaining = deadline - time.monotonic()
        if not retryable or remaining <= 0:
            raise AdmissionError(f"reserve_failed:{last_error}")
        time.sleep(min(delay, remaining))
        delay = min(delay * 2.0, 5.0)


def release(args: argparse.Namespace, lease_id: str, release_token: str) -> None:
    response = admission_request(
        args.socket,
        {
            "command": "release",
            "request": {"lease_id": lease_id, "release_token": release_token},
        },
        args.admission_timeout,
    )
    if response.get("ok") is not True or response.get("decision") != "allow":
        reasons = response.get("denied_reasons") or ["not_allowed"]
        raise AdmissionError("release_denied:" + ",".join(str(item) for item in reasons))


def wait_ready(child: subprocess.Popen[bytes], url: str, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        returncode = child.poll()
        if returncode is not None:
            raise RuntimeError(f"child_exited_before_ready:{returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise TimeoutError("child_readiness_timeout")


def signal_child_group(child: subprocess.Popen[bytes], signum: int) -> None:
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signum)
    except ProcessLookupError:
        pass


def normalize_returncode(returncode: int) -> int:
    return 128 + abs(returncode) if returncode < 0 else returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner-scoped cold-load admission entrypoint")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--workload-id", required=True)
    parser.add_argument("--activity", choices=["foreground", "background", "maintenance"], required=True)
    parser.add_argument("--class", dest="workload_class", choices=["probe", "light", "medium", "heavy", "sustained"], default="heavy")
    parser.add_argument("--kind", choices=["ai", "agent", "benchmark", "indexing", "generic"], default="ai")
    parser.add_argument("--latency", choices=["low", "balanced", "interactive"], default="interactive")
    parser.add_argument("--memory-demand-mib", type=float, required=True)
    parser.add_argument("--estimate-source", required=True)
    parser.add_argument("--estimate-confidence", required=True)
    parser.add_argument("--health-url", required=True)
    parser.add_argument("--health-timeout", type=float, default=120.0)
    parser.add_argument("--admission-timeout", type=float, default=15.0)
    parser.add_argument("--admission-wait", type=float, default=0.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("child command is required after --")

    child: subprocess.Popen[bytes] | None = None
    lease: tuple[str, str] | None = None
    forwarded_signal: int | None = None

    def forward(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal
        forwarded_signal = signum
        if child is not None:
            signal_child_group(child, signum)

    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGTERM, forward)

    try:
        lease = reserve(args, lambda: forwarded_signal is not None)
        if forwarded_signal is not None:
            return 128 + forwarded_signal
        child = subprocess.Popen(command, start_new_session=True)
        wait_ready(child, args.health_url, args.health_timeout)
        try:
            release(args, *lease)
            lease = None
        except AdmissionError as exc:
            print(f"owner cold-load lease release deferred to TTL: {exc}", file=sys.stderr)
        return normalize_returncode(child.wait())
    except (AdmissionError, OSError, RuntimeError, TimeoutError) as exc:
        print(f"owner cold-load start failed: {exc}", file=sys.stderr)
        if child is not None and child.poll() is None:
            signal_child_group(child, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                signal_child_group(child, signal.SIGKILL)
                child.wait()
        return 75
    finally:
        if lease is not None:
            try:
                release(args, *lease)
            except AdmissionError as exc:
                print(f"owner cold-load lease cleanup deferred to TTL: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
